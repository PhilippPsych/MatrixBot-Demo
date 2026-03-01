#![recursion_limit = "256"]
use std::{
    collections::{HashMap, VecDeque},
    net::SocketAddr,
    sync::{
        Arc,
        atomic::{AtomicU64, Ordering},
    },
    time::{SystemTime, UNIX_EPOCH},
};

use anyhow::{Context, Result, anyhow};
use axum::{
    Json, Router,
    extract::{Query, State},
    http::StatusCode,
    routing::{get, post},
};
use matrix_sdk::{
    Client, Room, RoomState, SessionMeta, SessionTokens,
    authentication::matrix::MatrixSession,
    config::SyncSettings,
    ruma::{
        DeviceId, OwnedRoomId, OwnedUserId, RoomId, UserId,
        events::{
            room::{
                member::StrippedRoomMemberEvent,
                message::{MessageType, OriginalSyncRoomMessageEvent, RoomMessageEventContent},
            },
        },
    },
    store::RoomLoadSettings,
};
use serde::{Deserialize, Serialize};
use tokio::sync::{Mutex, Notify, RwLock};
use tracing::{debug, error, info, warn};
use url::Url;

#[derive(Clone)]
struct AppState {
    client: Client,
    queue: Arc<EventQueue>,
    dm_rooms: Arc<RwLock<HashMap<String, OwnedRoomId>>>,
}

struct EventQueue {
    events: Mutex<VecDeque<QueuedEvent>>,
    notify: Notify,
    next_id: AtomicU64,
    max_size: usize,
}

impl EventQueue {
    fn new(max_size: usize) -> Self {
        Self {
            events: Mutex::new(VecDeque::new()),
            notify: Notify::new(),
            next_id: AtomicU64::new(1),
            max_size,
        }
    }

    async fn push(&self, mut event: QueuedEvent) {
        event.id = self.next_id.fetch_add(1, Ordering::SeqCst);

        let mut guard = self.events.lock().await;
        guard.push_back(event);
        while guard.len() > self.max_size {
            guard.pop_front();
        }
        drop(guard);

        self.notify.notify_waiters();
    }

    async fn after(&self, after: u64, limit: usize) -> Vec<QueuedEvent> {
        let guard = self.events.lock().await;
        guard
            .iter()
            .filter(|ev| ev.id > after)
            .take(limit)
            .cloned()
            .collect()
    }

    async fn latest_id(&self) -> u64 {
        let guard = self.events.lock().await;
        guard.back().map(|e| e.id).unwrap_or(0)
    }
}

#[derive(Debug, Clone, Serialize)]
struct QueuedEvent {
    id: u64,
    #[serde(rename = "type")]
    event_type: String,
    sender: String,
    room_id: String,
    event_id: Option<String>,
    timestamp: u64,
    message: Option<String>,
}

impl QueuedEvent {
    fn message(sender: String, room_id: String, event_id: String, message: String) -> Self {
        Self {
            id: 0,
            event_type: "message".to_owned(),
            sender,
            room_id,
            event_id: Some(event_id),
            timestamp: now_ms(),
            message: Some(message),
        }
    }

    fn invite(sender: String, room_id: String) -> Self {
        Self {
            id: 0,
            event_type: "invite".to_owned(),
            sender,
            room_id,
            event_id: None,
            timestamp: now_ms(),
            message: None,
        }
    }
}

#[derive(Debug, Deserialize)]
struct EventsQuery {
    after: Option<u64>,
    timeout_ms: Option<u64>,
    limit: Option<usize>,
}

#[derive(Debug, Serialize)]
struct EventsResponse {
    events: Vec<QueuedEvent>,
    next_after: u64,
}

#[derive(Debug, Deserialize)]
struct SendRequest {
    #[serde(alias = "user_id")]
    recipient: String,
    message: String,
}

#[derive(Debug, Serialize)]
struct SendResponse {
    ok: bool,
    room_id: String,
    event_id: String,
}

#[derive(Debug, Serialize)]
struct HealthResponse {
    ok: bool,
    user_id: Option<String>,
    device_id: Option<String>,
    queued_events: u64,
}

#[derive(Debug)]
struct Config {
    homeserver: String,
    user_id: String,
    access_token: Option<String>,
    password: Option<String>,
    device_id: Option<String>,
    device_display_name: String,
    store_path: String,
    store_passphrase: Option<String>,
    listen: SocketAddr,
}

impl Config {
    fn from_env() -> Result<Self> {
        let homeserver = required_env("MATRIX_HOMESERVER")?;
        let user_id = required_env("MATRIX_USER_ID")?;
        let access_token = std::env::var("MATRIX_ACCESS_TOKEN").ok().filter(|v| !v.trim().is_empty());
        let password = std::env::var("MATRIX_PASSWORD").ok().filter(|v| !v.trim().is_empty());
        let device_id = std::env::var("MATRIX_DEVICE_ID").ok().filter(|v| !v.trim().is_empty());

        if access_token.is_none() && password.is_none() {
            return Err(anyhow!(
                "Setze MATRIX_PASSWORD oder MATRIX_ACCESS_TOKEN für den Sidecar-Login"
            ));
        }

        let device_display_name = std::env::var("MATRIX_DEVICE_DISPLAY_NAME")
            .unwrap_or_else(|_| "Ella Bot Sidecar".to_owned());

        let store_path =
            std::env::var("MATRIX_SIDECAR_STORE").unwrap_or_else(|_| "./matrix_sidecar/store".to_owned());

        let store_passphrase =
            std::env::var("MATRIX_SIDECAR_STORE_PASSPHRASE").ok().filter(|v| !v.trim().is_empty());

        let listen = std::env::var("MATRIX_SIDECAR_LISTEN")
            .unwrap_or_else(|_| "127.0.0.1:8010".to_owned())
            .parse()
            .context("MATRIX_SIDECAR_LISTEN muss host:port sein")?;

        Ok(Self {
            homeserver,
            user_id,
            access_token,
            password,
            device_id,
            device_display_name,
            store_path,
            store_passphrase,
            listen,
        })
    }
}


async fn setup_cross_signing(client: &Client, user_id: &str, password: &str) -> Result<()> {
    use matrix_sdk::ruma::api::client::uiaa;
    
    let encryption = client.encryption();
    
    // Prüfen ob bereits aktiv
    if let Some(status) = encryption.cross_signing_status().await {
        if status.has_master && status.has_self_signing && status.has_user_signing {
            info!("Cross-signing already complete");
            return Ok(());
        }
    }
    
    info!("Bootstrapping cross-signing...");
    
    // Erst ohne Auth versuchen - Server gibt UIA-Challenge zurück
    if let Err(e) = encryption.bootstrap_cross_signing(None).await {
        if let Some(response) = e.as_uiaa_response() {
            info!("UIA required, authenticating with password...");
            let mut pw = uiaa::Password::new(
                uiaa::UserIdentifier::UserIdOrLocalpart(user_id.to_owned()),
                password.to_owned(),
            );
            pw.session = response.session.clone();
            
            encryption
                .bootstrap_cross_signing(Some(uiaa::AuthData::Password(pw)))
                .await
                .context("bootstrap_cross_signing with auth failed")?;
        } else {
            return Err(e.into());
        }
    }
    
    Ok(())
}

#[tokio::main]
async fn main() -> Result<()> {
    init_tracing();

    let cfg = Config::from_env()?;
    let client = build_client(&cfg).await?;
    login_or_restore(&client, &cfg).await?;

    // Cross-signing setup
    if let Some(password) = cfg.password.as_deref() {
        match setup_cross_signing(&client, &cfg.user_id, password).await {
            Ok(()) => info!("Cross-signing setup successful"),
            Err(e) => warn!("Cross-signing setup failed (non-fatal): {e:?}"),
        }
    }

    // Initial sync to populate state/store before we attach message handlers.
    client.sync_once(SyncSettings::default()).await.context("initial sync failed")?;

    let state = AppState {
        client: client.clone(),
        queue: Arc::new(EventQueue::new(5000)),
        dm_rooms: Arc::new(RwLock::new(HashMap::new())),
    };

    register_handlers(&state);

    let sync_client = client.clone();
    tokio::spawn(async move {
        if let Err(err) = sync_client.sync(SyncSettings::default()).await {
            error!("sync loop stopped: {err:?}");
        }
    });

    let app = Router::new()
        .route("/health", get(health))
        .route("/events", get(events))
        .route("/send", post(send))
        .with_state(state);

    let listener = tokio::net::TcpListener::bind(cfg.listen)
        .await
        .with_context(|| format!("failed to bind sidecar listen address {}", cfg.listen))?;

    info!("matrix sidecar listening on http://{}", cfg.listen);

    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await
        .context("sidecar server failed")?;

    Ok(())
}

fn init_tracing() {
    let filter = std::env::var("RUST_LOG").unwrap_or_else(|_| "info,matrix_sdk=warn".to_owned());
    tracing_subscriber::fmt()
        .with_env_filter(filter)
        .with_target(false)
        .compact()
        .init();
}

async fn build_client(cfg: &Config) -> Result<Client> {
    let homeserver = Url::parse(&cfg.homeserver)
        .with_context(|| format!("MATRIX_HOMESERVER ist keine valide URL: {}", cfg.homeserver))?;

    let client = Client::builder()
        .homeserver_url(homeserver)
        .sqlite_store(&cfg.store_path, cfg.store_passphrase.as_deref())
        .build()
        .await
        .context("failed to build matrix client")?;

    Ok(client)
}

async fn login_or_restore(client: &Client, cfg: &Config) -> Result<()> {
    if let Some(password) = cfg.password.as_deref() {
        info!("logging in via username/password");
        let mut login = client
            .matrix_auth()
            .login_username(&cfg.user_id, password)
            .initial_device_display_name(&cfg.device_display_name);

        if let Some(device_id) = cfg.device_id.as_deref() {
            login = login.device_id(device_id);
        }

        let response = login.send().await.context("matrix login failed")?;
        info!("logged in as {} with device {}", response.user_id, response.device_id);
        return Ok(());
    }

    let access_token = cfg
        .access_token
        .as_ref()
        .ok_or_else(|| anyhow!("MATRIX_ACCESS_TOKEN fehlt"))?
        .to_owned();

    let device_id = cfg
        .device_id
        .clone()
        .ok_or_else(|| anyhow!("MATRIX_DEVICE_ID fehlt für Access-Token-Login"))?;

    info!("restoring session via access token for device {}", device_id);

    let session = MatrixSession {
        meta: SessionMeta {
            user_id: UserId::parse(cfg.user_id.clone())?.to_owned(),
            device_id: <&DeviceId>::from(device_id.as_str()).to_owned(),
        },
        tokens: SessionTokens {
            access_token,
            refresh_token: None,
        },
    };

    client
        .matrix_auth()
        .restore_session(session, RoomLoadSettings::default())
        .await
        .context("restore_session failed")?;

    Ok(())
}

fn register_handlers(state: &AppState) {
    let message_state = state.clone();
    state.client.add_event_handler(move |ev: OriginalSyncRoomMessageEvent, room: Room, client: Client| {
        let state = message_state.clone();
        async move {
            if let Some(own_user) = client.user_id() {
                if ev.sender == own_user {
                    return;
                }
            }

            let body = match &ev.content.msgtype {
                MessageType::Text(c) => c.body.clone(),
                _ => return,
            };

            {
                let mut map = state.dm_rooms.write().await;
                map.insert(ev.sender.to_string(), room.room_id().to_owned());
            }

            let event = QueuedEvent::message(
                ev.sender.to_string(),
                room.room_id().to_string(),
                ev.event_id.to_string(),
                body,
            );
            state.queue.push(event).await;
        }
    });

    let invite_state = state.clone();
    state.client.add_event_handler(move |ev: StrippedRoomMemberEvent, room: Room, client: Client| {
        let state = invite_state.clone();
        async move {
            let Some(own_user) = client.user_id() else {
                return;
            };

            if ev.state_key != own_user {
                return;
            }

            if room.state() != RoomState::Invited {
                return;
            }

            let room_id = room.room_id().to_owned();
            let sender = ev.sender.to_string();

            info!("joining invited room {} from {}", room_id, sender);
            match room.join().await {
                Ok(()) => {
                    state.queue.push(QueuedEvent::invite(sender, room_id.to_string())).await;
                }
                Err(err) => {
                    warn!("failed to join invited room {}: {err:?}", room_id);
                }
            }
        }
    });
}

async fn health(State(state): State<AppState>) -> Json<HealthResponse> {
    Json(HealthResponse {
        ok: true,
        user_id: state.client.user_id().map(ToString::to_string),
        device_id: state.client.device_id().map(ToString::to_string),
        queued_events: state.queue.latest_id().await,
    })
}

async fn events(State(state): State<AppState>, Query(query): Query<EventsQuery>) -> Json<EventsResponse> {
    let after = query.after.unwrap_or(0);
    let timeout_ms = query.timeout_ms.unwrap_or(30_000).min(120_000);
    let limit = query.limit.unwrap_or(50).clamp(1, 500);

    let deadline = tokio::time::Instant::now() + tokio::time::Duration::from_millis(timeout_ms);

    let events = loop {
        let found = state.queue.after(after, limit).await;
        if !found.is_empty() {
            break found;
        }

        let now = tokio::time::Instant::now();
        if now >= deadline {
            break Vec::new();
        }

        let wait_for = deadline.saturating_duration_since(now);
        let notified = tokio::time::timeout(wait_for, state.queue.notify.notified()).await;
        if notified.is_err() {
            break Vec::new();
        }
    };

    let next_after = events.last().map(|e| e.id).unwrap_or(after);

    Json(EventsResponse { events, next_after })
}

async fn send(
    State(state): State<AppState>,
    Json(payload): Json<SendRequest>,
) -> std::result::Result<Json<SendResponse>, (StatusCode, String)> {
    match send_inner(&state, payload).await {
        Ok(response) => Ok(Json(response)),
        Err(err) => {
            error!("send failed: {err:?}");
            Err((StatusCode::BAD_GATEWAY, err.to_string()))
        }
    }
}

async fn send_inner(state: &AppState, payload: SendRequest) -> Result<SendResponse> {
    let recipient: OwnedUserId = UserId::parse(payload.recipient.clone())?.to_owned();

    let room = ensure_dm_room(state, &recipient).await?;

    let content = RoomMessageEventContent::text_plain(payload.message);
    let response = room.send(content).await.context("room_send failed")?;

    Ok(SendResponse {
        ok: true,
        room_id: room.room_id().to_string(),
        event_id: response.event_id.to_string(),
    })
}

async fn ensure_dm_room(state: &AppState, recipient: &UserId) -> Result<Room> {
    if let Some(room_id) = state.dm_rooms.read().await.get(recipient.as_str()).cloned()
        && let Some(room) = state.client.get_room(&room_id)
    {
        return Ok(room);
    }

    if let Some(room) = state.client.get_dm_room(recipient) {
        state
            .dm_rooms
            .write()
            .await
            .insert(recipient.to_string(), room.room_id().to_owned());
        return Ok(room);
    }

    info!("creating DM room for {}", recipient);
    let room = state.client.create_dm(recipient).await.context("create_dm failed")?;
    state
        .dm_rooms
        .write()
        .await
        .insert(recipient.to_string(), room.room_id().to_owned());

    Ok(room)
}

fn required_env(key: &str) -> Result<String> {
    std::env::var(key).map_err(|_| anyhow!("fehlende Umgebungsvariable: {key}"))
}

async fn shutdown_signal() {
    #[cfg(unix)]
    {
        let mut sigterm = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
            .expect("failed to install SIGTERM handler");

        tokio::select! {
            _ = tokio::signal::ctrl_c() => {},
            _ = sigterm.recv() => {},
        }
    }

    #[cfg(not(unix))]
    {
        let _ = tokio::signal::ctrl_c().await;
    }

    info!("shutdown signal received");
}

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

#[allow(dead_code)]
fn _as_room_id(room_id: &str) -> Result<OwnedRoomId> {
    Ok(RoomId::parse(room_id)?.to_owned())
}
