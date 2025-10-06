#!/usr/bin/env python3
"""
Web-based Live Chat Interface using Streamlit.
This provides a beautiful web interface for the AI chatbot.
"""

import streamlit as st
import asyncio
import aiohttp
import json
import uuid
from datetime import datetime
import time
import os
from pathlib import Path
import subprocess
import shutil
import platform
from google.oauth2 import id_token as google_id_token
from google.auth.transport.requests import Request as GoogleAuthRequest

# Page config must be the first Streamlit command
st.set_page_config(
    page_title="I Get Happy - Chat with Mindy",
    page_icon="😊",
    layout="wide"
)

# Helper: simulate streaming by yielding small chunks for the UI
def _simulate_streaming(text: str, chunk_size: int = 6, delay_seconds: float = 0.02):
    """Yield small chunks of text to simulate streaming in the UI."""
    if not text:
        return
    for i in range(0, len(text), chunk_size):
        yield text[i:i+chunk_size]
        time.sleep(delay_seconds)

def _default_base_url() -> str:
    """Resolve a default backend URL from env, secrets, or localhost."""
    base = os.getenv("BASE_URL")
    if base:
        return base
    try:
        home_secrets = Path.home() / ".streamlit" / "secrets.toml"
        local_secrets = Path(__file__).parent / ".streamlit" / "secrets.toml"
        if home_secrets.exists() or local_secrets.exists():
            if "BASE_URL" in st.secrets:
                return str(st.secrets["BASE_URL"])
    except Exception:
        pass
    return "https://igethappy-chatbot-790537847272.us-central1.run.app"

# Initialize a user-editable backend URL in session state
if "backend_url" not in st.session_state:
    st.session_state.backend_url = _default_base_url()

def get_backend_url() -> str:
    """Get the current backend URL, falling back to default if missing."""
    return st.session_state.get("backend_url") or _default_base_url()

class WebChatInterface:
    def __init__(self, base_url: str = None):
        self.session = None
        self.base_url = base_url or get_backend_url()
        self._cached_id_token: str | None = None
        self._cached_id_token_expiry: float = 0.0
        
    def _fetch_id_token_via_gcloud(self) -> str:
        """Fallback: use gcloud to impersonate a service account and mint an ID token."""
        audience = self.base_url
        impersonate_sa = os.getenv("GCP_IMPERSONATE_SA", "fastapi-invoker-sa@igethappy-dev.iam.gserviceaccount.com")
        # Resolve gcloud executable (supports Windows .cmd)
        gcloud_path = os.getenv("GCLOUD_PATH") or shutil.which("gcloud") or shutil.which("gcloud.cmd")
        if not gcloud_path:
            raise RuntimeError("gcloud not found. Install Google Cloud SDK, add it to PATH, or set GCLOUD_PATH to gcloud executable.")
        cmd = [
            gcloud_path,
            "auth",
            "print-identity-token",
            f"--impersonate-service-account={impersonate_sa}",
            f"--audiences={audience}",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            stderr = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(f"gcloud print-identity-token failed: {stderr}")
        token = (proc.stdout or "").strip()
        if not token:
            raise RuntimeError("gcloud did not return an ID token")
        return token

    async def _get_id_token(self) -> str:
        """Get an ID token, preferring cached value, then google-auth, then gcloud."""
        now = time.time()
        if self._cached_id_token and now < self._cached_id_token_expiry:
            return self._cached_id_token
        # Try google-auth with ADC first
        try:
            token = await asyncio.to_thread(google_id_token.fetch_id_token, GoogleAuthRequest(), self.base_url)
        except Exception:
            # Fallback to gcloud impersonation
            token = await asyncio.to_thread(self._fetch_id_token_via_gcloud)
        self._cached_id_token = token
        self._cached_id_token_expiry = now + 300.0  # refresh every 5 minutes
        return token

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def send_message(self, message: str, conversation_id: str = None, token: str = None):
        """Send a message to the chatbot."""
        client_user_id = st.session_state.get("user_id") or st.session_state.get("client_user_id")
        payload = {
            "conversation_id": str(conversation_id) if conversation_id else None,
            "message": message
        }
        
        headers = {"Content-Type": "application/json"}
        # Attach app JWT in X-User-Token so Authorization can carry Cloud Run ID token
        if token:
            headers["X-User-Token"] = f"Bearer {token}"
        if st.session_state.get("api_key"):
            headers["X-API-Key"] = st.session_state.api_key
        # Always include Cloud Run ID token (service is private)
        id_tok = await self._get_id_token()
        headers["Authorization"] = f"Bearer {id_tok}"
        
        try:
            async with self.session.post(
                f"{self.base_url}/api/ai/chat",
                json=payload,
                headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                else:
                    error_text = await response.text()
                    return {"error": f"Error {response.status}: {error_text}"}
        except Exception as e:
            return {"error": f"Connection error: {str(e)}. Make sure the backend is running on {self.base_url}"}

    async def start_conversation(self, token: str = None):
        """Start a new conversation and receive the assistant greeting."""
        headers = {"Content-Type": "application/json"}
        # Attach app JWT separately and Cloud Run ID token in Authorization
        if token:
            headers["X-User-Token"] = f"Bearer {token}"
        if st.session_state.get("api_key"):
            headers["X-API-Key"] = st.session_state.api_key
        client_user_id = st.session_state.get("user_id") or st.session_state.get("client_user_id")
        id_tok = await self._get_id_token()
        headers["Authorization"] = f"Bearer {id_tok}"
        try:
            async with self.session.post(
                f"{self.base_url}/api/ai/start-conversation",
                json={"client_user_id": str(client_user_id)},
                headers=headers
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    return {"error": f"Error {response.status}: {error_text}"}
        except Exception as e:
            return {"error": f"Connection error: {str(e)}. Make sure the backend is running on {self.base_url}"}

    async def login_user(self, email: str, password: str):
        """Login user and return token payload or error."""
        try:
            async with aiohttp.ClientSession() as s:
                # Cloud Run ID token required even for auth endpoints on private service
                id_tok = await self._get_id_token()
                async with s.post(
                    f"{self.base_url}/api/auth/login",
                    json={"email": email, "password": password},
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {id_tok}"}
                ) as response:
                    try:
                        data = await response.json()
                    except Exception:
                        data = {"detail": await response.text()}
                    if response.status == 200:
                        return {"access_token": data.get("access_token"), "user_id": data.get("user_id")}
                    return {"error": data.get("detail", "Login failed")}
        except Exception as e:
            return {"error": f"Connection error: {str(e)}. Make sure the backend is running on {self.base_url}"}

    async def register_user(self, email: str, password: str, first_name: str, last_name: str):
        """Register a new user."""
        try:
            async with aiohttp.ClientSession() as s:
                id_tok = await self._get_id_token()
                async with s.post(
                    f"{self.base_url}/api/auth/register",
                    json={
                        "email": email,
                        "password": password,
                        "first_name": first_name,
                        "last_name": last_name
                    },
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {id_tok}"}
                ) as response:
                    try:
                        data = await response.json()
                    except Exception:
                        data = {"detail": await response.text()}
                    if response.status == 200:
                        return {"access_token": data.get("access_token"), "user_id": data.get("user_id")}
                    return {"error": data.get("detail", "Registration failed")}
        except Exception as e:
            return {"error": f"Connection error: {str(e)}. Make sure the backend is running on {self.base_url}"}

    async def health_check(self):
        """Ping backend health endpoint."""
        try:
            async with aiohttp.ClientSession() as s:
                id_tok = await self._get_id_token()
                async with s.get(f"{self.base_url}/health", headers={"Authorization": f"Bearer {id_tok}"}) as response:
                    text = await response.text()
                    return {"status": response.status, "body": text}
        except Exception as e:
            return {"status": None, "error": str(e)}

def run_web_chat():
    """Run the web chat interface."""
    st.title("😊 I Get Happy")
    st.subheader("Chat with Mindy, your AI Mental Health Assistant")
    
    # Initialize session state
    if "conversation_id" not in st.session_state:
        st.session_state.conversation_id = None
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "token" not in st.session_state:
        st.session_state.token = None
    if "user_info" not in st.session_state:
        st.session_state.user_info = None
    if "greeted" not in st.session_state:
        st.session_state.greeted = False
    if "user_id" not in st.session_state:
        st.session_state.user_id = None
    if "client_user_id" not in st.session_state:
        st.session_state.client_user_id = str(uuid.uuid4())
    if "api_key" not in st.session_state:
        st.session_state.api_key = ""
    
    # Authentication section
    if not st.session_state.token:
        st.header("🔐 Get Started")
        
        # Create tabs for login and register
        tab1, tab2 = st.tabs(["Login", "Register"])
        
        with tab1:
            with st.form("login_form"):
                st.subheader("Login to your account")
                email = st.text_input("Email", placeholder="your.email@example.com")
                password = st.text_input("Password", type="password")
                submit_login = st.form_submit_button("Login", type="primary")
                
                if submit_login:
                    if not email or not password:
                        st.error("Please fill in both fields")
                    else:
                        with st.spinner("Logging in..."):
                            result = asyncio.run(login_user(email, password))
                            if "error" in result:
                                st.error(f"❌ {result['error']}")
                            else:
                                st.session_state.token = result["access_token"]
                                st.session_state.user_id = str(result.get("user_id")) if result.get("user_id") else st.session_state.user_id
                                st.session_state.user_info = {"email": email}
                                st.success("✅ Login successful!")
                                st.rerun()
        
        with tab2:
            with st.form("register_form"):
                st.subheader("Create a new account")
                first_name = st.text_input("First Name")
                last_name = st.text_input("Last Name")
                email = st.text_input("Email", placeholder="your.email@example.com")
                password = st.text_input("Password", type="password")
                confirm_password = st.text_input("Confirm Password", type="password")
                submit_register = st.form_submit_button("Register", type="primary")
                
                if submit_register:
                    if not all([first_name, last_name, email, password, confirm_password]):
                        st.error("Please fill in all fields")
                    elif password != confirm_password:
                        st.error("Passwords do not match")
                    else:
                        with st.spinner("Creating account..."):
                            result = asyncio.run(register_user(email, password, first_name, last_name))
                            if "error" in result:
                                st.error(f"❌ {result['error']}")
                            else:
                                st.session_state.token = result["access_token"]
                                st.session_state.user_id = str(result.get("user_id")) if result.get("user_id") else st.session_state.user_id
                                st.session_state.user_info = {"email": email, "first_name": first_name, "last_name": last_name}
                                st.success("✅ Account created successfully!")
                                st.rerun()
        return
    
    # Sidebar for controls
    with st.sidebar:
        st.header("🎛️ Controls")
        # Backend URL control
        _current_backend = st.text_input("Backend URL", value=get_backend_url())
        if _current_backend and _current_backend != st.session_state.backend_url:
            st.session_state.backend_url = _current_backend
            st.rerun()
        _api_key_val = st.text_input("X-API-Key (test only)", value=st.session_state.api_key, type="password")
        if _api_key_val != st.session_state.api_key:
            st.session_state.api_key = _api_key_val
            st.rerun()
        
        if st.button("🆕 New Conversation"):
            st.session_state.conversation_id = None
            st.session_state.messages = []
            st.session_state.greeted = False
            st.rerun()
        
        if st.button("🚪 Logout"):
            st.session_state.token = None
            st.session_state.user_info = None
            st.session_state.conversation_id = None
            st.session_state.messages = []
            st.session_state.greeted = False
            st.rerun()
        
        st.header("ℹ️ Info")
        if st.session_state.user_info:
            st.write(f"**User:** {st.session_state.user_info.get('email', 'Unknown')}")
        st.write(f"**Backend:** {get_backend_url()}")
        if st.button("🔌 Check backend connection"):
            result = asyncio.run(check_backend())
            if result.get("status") == 200:
                st.success("Backend reachable ✅")
            else:
                st.error(f"Backend not reachable. Status: {result.get('status')}, Error: {result.get('error', result.get('body',''))}")
        st.write("**Features:**")
        st.write("• Personalized AI responses")
        st.write("• Conversation history")
        st.write("• Mental health support")
        st.write("• HIPAA compliant")
    
    # Offer assistant-initiated greeting for new sessions
    if st.session_state.conversation_id is None and st.button("👋 Start conversation"):
        with st.spinner("Starting a conversation..."):
            result = asyncio.run(start_conversation())
            if result and "error" not in result:
                st.session_state.conversation_id = result["conversation_id"]
                reply_text = result.get("ai_response") or result.get("response") or ""
                st.session_state.messages.append({"role": "assistant", "content": reply_text})
                st.session_state.greeted = True
                st.rerun()

    # Auto-start once on first load into an empty chat
    if st.session_state.conversation_id is None and not st.session_state.greeted:
        with st.spinner("Starting a conversation..."):
            result = asyncio.run(start_conversation())
            if result and "error" not in result:
                st.session_state.conversation_id = result["conversation_id"]
                reply_text = result.get("ai_response") or result.get("response") or ""
                st.session_state.messages.append({"role": "assistant", "content": reply_text})
                st.session_state.greeted = True
                st.rerun()
    
    # Main chat interface
    st.header("💬 Chat with Mindy")
    
    # Display messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
    
    # Chat input
    if prompt := st.chat_input("What's on your mind? How can I help you feel happier today?"):
        # Ensure a conversation exists before sending the first message
        if st.session_state.conversation_id is None:
            with st.spinner("Starting a conversation..."):
                result = asyncio.run(start_conversation())
                if result and "error" not in result:
                    st.session_state.conversation_id = result["conversation_id"]
                    reply_text = result.get("ai_response") or result.get("response") or ""
                    st.session_state.messages.append({"role": "assistant", "content": reply_text})
                else:
                    st.error(result.get("error", "Failed to start conversation"))
                    st.stop()
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Display user message
        with st.chat_message("user"):
            st.write(prompt)
        
        # Get AI response (simulate streaming to UI)
        with st.chat_message("assistant"):
            with st.spinner("Mindy is thinking..."):
                response = asyncio.run(get_ai_response(prompt))
            
            if "error" in response:
                st.error(response["error"])
            else:
                full_text = response.get("ai_response") or response.get("response") or ""
                # Stream chunk-by-chunk to simulate typing using Streamlit's write_stream
                st.write_stream(_simulate_streaming(full_text))
                # Finalize message
                st.session_state.conversation_id = response["conversation_id"]
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": full_text
                })

async def get_ai_response(message: str):
    """Get AI response for a message."""
    async with WebChatInterface(base_url=get_backend_url()) as chat:
        return await chat.send_message(message, st.session_state.conversation_id, st.session_state.token)

async def start_conversation():
    """Start a new conversation and get the greeting."""
    async with WebChatInterface(base_url=get_backend_url()) as chat:
        return await chat.start_conversation(st.session_state.token)

async def login_user(email: str, password: str):
    """Perform login and return token payload or error."""
    async with WebChatInterface(base_url=get_backend_url()) as chat:
        return await chat.login_user(email, password)

async def register_user(email: str, password: str, first_name: str, last_name: str):
    """Perform registration and return token payload or error."""
    async with WebChatInterface(base_url=get_backend_url()) as chat:
        return await chat.register_user(email, password, first_name, last_name)

async def check_backend():
    """Check backend /health endpoint."""
    async with WebChatInterface(base_url=get_backend_url()) as chat:
        return await chat.health_check()

if __name__ == "__main__":
    run_web_chat()
