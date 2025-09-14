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

# API Configuration - configurable via environment variable for Cloud Run
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

class WebChatInterface:
    def __init__(self):
        self.session = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def send_message(self, message: str, conversation_id: str = None, token: str = None):
        """Send a message to the chatbot."""
        payload = {
            "conversation_id": conversation_id,
            "message": message
        }
        
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        
        try:
            async with self.session.post(
                f"{BASE_URL}/api/ai/chat",
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
            return {"error": f"Connection error: {str(e)}. Make sure the backend is running on {BASE_URL}"}

    async def start_conversation(self, token: str = None):
        """Start a new conversation and receive the assistant greeting."""
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            async with self.session.post(f"{BASE_URL}/api/ai/start-conversation", headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    return {"error": f"Error {response.status}: {error_text}"}
        except Exception as e:
            return {"error": f"Connection error: {str(e)}. Make sure the backend is running on {BASE_URL}"}

    async def login_user(self, email: str, password: str):
        """Login user and return token payload or error."""
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    f"{BASE_URL}/api/auth/login",
                    json={"email": email, "password": password},
                    headers={"Content-Type": "application/json"}
                ) as response:
                    try:
                        data = await response.json()
                    except Exception:
                        data = {"detail": await response.text()}
                    if response.status == 200:
                        return {"access_token": data.get("access_token")}
                    return {"error": data.get("detail", "Login failed")}
        except Exception as e:
            return {"error": f"Connection error: {str(e)}. Make sure the backend is running on {BASE_URL}"}

    async def register_user(self, email: str, password: str, first_name: str, last_name: str):
        """Register a new user."""
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    f"{BASE_URL}/api/auth/register",
                    json={
                        "email": email,
                        "password": password,
                        "first_name": first_name,
                        "last_name": last_name
                    },
                    headers={"Content-Type": "application/json"}
                ) as response:
                    try:
                        data = await response.json()
                    except Exception:
                        data = {"detail": await response.text()}
                    if response.status == 200:
                        return {"access_token": data.get("access_token")}
                    return {"error": data.get("detail", "Registration failed")}
        except Exception as e:
            return {"error": f"Connection error: {str(e)}. Make sure the backend is running on {BASE_URL}"}

def run_web_chat():
    """Run the web chat interface."""
    st.set_page_config(
        page_title="I Get Happy - Chat with Mindy",
        page_icon="😊",
        layout="wide"
    )
    
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
                                st.session_state.user_info = {"email": email, "first_name": first_name, "last_name": last_name}
                                st.success("✅ Account created successfully!")
                                st.rerun()
        return
    
    # Sidebar for controls
    with st.sidebar:
        st.header("🎛️ Controls")
        
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
                st.session_state.messages.append({"role": "assistant", "content": result["response"]})
                st.session_state.greeted = True
                st.rerun()

    # Auto-start once on first load into an empty chat
    if st.session_state.conversation_id is None and not st.session_state.greeted:
        with st.spinner("Starting a conversation..."):
            result = asyncio.run(start_conversation())
            if result and "error" not in result:
                st.session_state.conversation_id = result["conversation_id"]
                st.session_state.messages.append({"role": "assistant", "content": result["response"]})
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
                    st.session_state.messages.append({"role": "assistant", "content": result["response"]})
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
                full_text = response["response"] or ""
                placeholder = st.empty()
                streamed = ""
                # Stream chunk-by-chunk to simulate typing
                for i in range(0, len(full_text), 6):
                    streamed = full_text[:i+6]
                    placeholder.markdown(streamed)
                    time.sleep(0.02)
                # Finalize message
                st.session_state.conversation_id = response["conversation_id"]
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": full_text
                })

async def get_ai_response(message: str):
    """Get AI response for a message."""
    async with WebChatInterface() as chat:
        return await chat.send_message(message, st.session_state.conversation_id, st.session_state.token)

async def start_conversation():
    """Start a new conversation and get the greeting."""
    async with WebChatInterface() as chat:
        return await chat.start_conversation(st.session_state.token)

async def login_user(email: str, password: str):
    """Perform login and return token payload or error."""
    async with WebChatInterface() as chat:
        return await chat.login_user(email, password)

async def register_user(email: str, password: str, first_name: str, last_name: str):
    """Perform registration and return token payload or error."""
    async with WebChatInterface() as chat:
        return await chat.register_user(email, password, first_name, last_name)

if __name__ == "__main__":
    run_web_chat()
