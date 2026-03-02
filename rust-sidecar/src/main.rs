use anyhow::Result;
use axum::{
    extract::State,
    routing::{get, post},
    Json, Router,
};
use matrix_sdk::{
    config::SyncSettings,
    room::Room,
    ruma::{
        events::room::message::{MessageType, OriginalSyncRoomMessageEvent, RoomMessageEventContent},
        OwnedUserId, UserId,
    },
    Client,
};
use serde::{Deserialize, Serialize};
use std::{
    collections::VecDeque,
    sync::Arc,
};
use tokio::sync::Mutex;
use tracing::{info, warn};

#[derive(Clone)]
struct AppState {
    client: Client,
    incoming_messages: Arc<Mutex<VecDeque<IncomingMessage>>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct IncomingMessage {
    sender: String,
    body: String,
    room_id: String,
}

#[derive(Debug, Deserialize)]
struct SendMessageRequest {
    user_id: String,
    message: String,
}

#[derive(Debug, Serialize)]
struct SendMessageResponse {
    success: bool,
    error: Option<String>,
}

#[derive(Debug, Serialize)]
struct HealthResponse {
    status: String,
    user_id: String,
    device_id: String,
    cross_signing: bool,
}

async fn health(State(state): State<AppState>) -> Json<HealthResponse> {
    let user_id = state.client.user_id().map(|u| u.to_string()).unwrap_or_default();
    let device_id = state.client.device_id().map(|d| d.to_string()).unwrap_or_default();
    let cross_signing = state.client.encryption()
        .cross_signing_status()
        .await
        .map(|s| s.is_complete())
        .unwrap_or(false);
    Json(HealthResponse {
        status: "ok".to_string(),
        user_id,
        device_id,
        cross_signing,
    })
}

async fn get_messages(State(state): State<AppState>) -> Json<Vec<IncomingMessage>> {
    let mut queue = state.incoming_messages.lock().await;
    let messages: Vec<_> = queue.drain(..).collect();
    Json(messages)
}

async fn send_message(
    State(state): State<AppState>,
    Json(req): Json<SendMessageRequest>,
) -> Json<SendMessageResponse> {
    let target_user: OwnedUserId = match req.user_id.parse() {
        Ok(u) => u,
        Err(e) => {
            return Json(SendMessageResponse {
                success: false,
                error: Some(format!("Invalid user_id: {}", e)),
            });
        }
    };

    let room = match find_or_create_dm(&state.client, &target_user).await {
        Ok(r) => r,
        Err(e) => {
            return Json(SendMessageResponse {
                success: false,
                error: Some(format!("Failed to get/create room: {}", e)),
            });
        }
    };

    let content = RoomMessageEventContent::text_plain(&req.message);
    match room.send(content).await {
        Ok(_) => Json(SendMessageResponse {
            success: true,
            error: None,
        }),
        Err(e) => Json(SendMessageResponse {
            success: false,
            error: Some(format!("Failed to send: {}", e)),
        }),
    }
}

async fn find_or_create_dm(client: &Client, user_id: &UserId) -> Result<Room> {
    for room in client.joined_rooms() {
        if room.is_direct().await.unwrap_or(false) {
            let members = room.members(matrix_sdk::RoomMemberships::ACTIVE).await?;
            if members.len() == 2 && members.iter().any(|m| m.user_id() == user_id) {
                return Ok(Room::from(room));
            }
        }
    }

    let mut request = matrix_sdk::ruma::api::client::room::create_room::v3::Request::new();
    request.is_direct = true;
    request.invite = vec![user_id.to_owned()];
    request.preset = Some(matrix_sdk::ruma::api::client::room::create_room::v3::RoomPreset::TrustedPrivateChat);
    
    let response = client.create_room(request).await?;
    let room = client.get_room(response.room_id()).ok_or_else(|| anyhow::anyhow!("Room not found"))?;
    
    Ok(room)
}

async fn setup_cross_signing(client: &Client) -> Result<()> {
    info!("Checking cross-signing status...");
    
    let encryption = client.encryption();
    
    // Check current status
    if let Some(status) = encryption.cross_signing_status().await {
        info!("Cross-signing status: has_master={}, has_self_signing={}, has_user_signing={}", 
              status.has_master, status.has_self_signing, status.has_user_signing);
        
        if status.is_complete() {
            info!("Cross-signing already complete!");
            return Ok(());
        }
    }
    
    // Try to bootstrap cross-signing
    info!("Bootstrapping cross-signing...");
    encryption.bootstrap_cross_signing(None).await?;
    
    info!("Cross-signing bootstrap complete!");
    Ok(())
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt::init();

    let homeserver = std::env::var("MATRIX_HOMESERVER").unwrap_or_else(|_| "https://demokratiebot.de".to_string());
    let username = std::env::var("MATRIX_USERNAME").unwrap_or_else(|_| "ella".to_string());
    let password = std::env::var("MATRIX_PASSWORD").expect("MATRIX_PASSWORD required");
    let store_path = std::env::var("MATRIX_STORE_PATH").unwrap_or_else(|_| "./matrix_store".to_string());
    let listen_addr = std::env::var("LISTEN_ADDR").unwrap_or_else(|_| "127.0.0.1:8010".to_string());

    info!("Starting Ella Sidecar...");
    info!("Homeserver: {}", homeserver);
    info!("Username: {}", username);

    let client: Client = Client::builder()
        .homeserver_url(&homeserver)
        .sqlite_store(&store_path, None)
        .build()
        .await?;

    client
        .matrix_auth()
        .login_username(&username, &password)
        .initial_device_display_name("Ella-Bot Rust")
        .send()
        .await?;

    info!("Logged in as {} on device {:?}", client.user_id().unwrap(), client.device_id());

    // Initial sync
    info!("Performing initial sync...");
    client.sync_once(SyncSettings::default()).await?;
    info!("Initial sync complete");

    // Setup cross-signing
    if let Err(e) = setup_cross_signing(&client).await {
        warn!("Cross-signing setup failed: {}. Continuing anyway...", e);
    }

    let incoming_messages: Arc<Mutex<VecDeque<IncomingMessage>>> = Arc::new(Mutex::new(VecDeque::new()));
    
    let state = AppState {
        client: client.clone(),
        incoming_messages: incoming_messages.clone(),
    };

    let messages_for_handler = incoming_messages.clone();
    client.add_event_handler(move |ev: OriginalSyncRoomMessageEvent, room: Room| {
        let messages = messages_for_handler.clone();
        async move {
            if let MessageType::Text(text) = &ev.content.msgtype {
                let msg = IncomingMessage {
                    sender: ev.sender.to_string(),
                    body: text.body.clone(),
                    room_id: room.room_id().to_string(),
                };
                info!("Received message from {}: {}", msg.sender, msg.body);
                messages.lock().await.push_back(msg);
            }
        }
    });

    client.add_event_handler(|ev: matrix_sdk::ruma::events::room::member::StrippedRoomMemberEvent, room: Room, client: Client| async move {
        if ev.content.membership == matrix_sdk::ruma::events::room::member::MembershipState::Invite {
            if let Some(user_id) = client.user_id() {
                if ev.state_key == user_id {
                    info!("Auto-joining room {}", room.room_id());
                    let _ = room.join().await;
                }
            }
        }
    });

    let sync_client = client.clone();
    tokio::spawn(async move {
        let _ = sync_client.sync(SyncSettings::default()).await;
    });

    let app = Router::new()
        .route("/health", get(health))
        .route("/messages", get(get_messages))
        .route("/send", post(send_message))
        .with_state(state);

    info!("HTTP API listening on {}", listen_addr);
    let listener = tokio::net::TcpListener::bind(&listen_addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}
