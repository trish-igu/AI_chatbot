#!/usr/bin/env python3
"""
Authentication Frontend using Streamlit.
Provides login and registration interface for the chatbot.
"""

import streamlit as st
import requests
import json
from datetime import datetime

# API Configuration
BASE_URL = "http://localhost:8000"

def login_user(email: str, password: str):
    """Login user and return token."""
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": password}
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": response.json().get("detail", "Login failed")}
    except Exception as e:
        return {"error": f"Connection error: {str(e)}"}

def register_user(email: str, password: str, first_name: str = None, last_name: str = None, 
                 display_name: str = None, phone_number: str = None, is_caregiver: bool = False):
    """Register new user."""
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": email, 
                "password": password,
                "first_name": first_name,
                "last_name": last_name,
                "display_name": display_name,
                "phone_number": phone_number,
                "is_caregiver": is_caregiver
            }
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": response.json().get("detail", "Registration failed")}
    except Exception as e:
        return {"error": f"Connection error: {str(e)}"}

def get_user_profile(token: str):
    """Get user profile."""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
        
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": response.json().get("detail", "Failed to get profile")}
    except Exception as e:
        return {"error": f"Connection error: {str(e)}"}

def main():
    st.set_page_config(
        page_title="I Get Happy - Authentication",
        page_icon="😊",
        layout="centered"
    )
    
    st.title("😊 I Get Happy")
    st.subheader("Mental Health Assistant - Authentication")
    
    # Initialize session state
    if "token" not in st.session_state:
        st.session_state.token = None
    if "user_profile" not in st.session_state:
        st.session_state.user_profile = None
    
    # Check if user is already logged in
    if st.session_state.token:
        st.success("✅ You are logged in!")
        
        # Get user profile
        if not st.session_state.user_profile:
            profile = get_user_profile(st.session_state.token)
            if "error" not in profile:
                st.session_state.user_profile = profile
        
        if st.session_state.user_profile:
            col1, col2 = st.columns([2, 1])
            with col1:
                display_name = st.session_state.user_profile.get('display_name') or st.session_state.user_profile.get('email', 'User')
                st.write(f"**Welcome, {display_name}!**")
                st.write(f"Email: {st.session_state.user_profile.get('email', 'N/A')}")
                st.write(f"Account created: {st.session_state.user_profile['created_at'][:10]}")
                if st.session_state.user_profile.get('is_caregiver'):
                    st.write("👨‍👩‍👧‍👦 Caregiver Account")
            
            with col2:
                if st.button("🚪 Logout"):
                    st.session_state.token = None
                    st.session_state.user_profile = None
                    st.rerun()
        
        # Navigation to chat
        st.markdown("---")
        st.markdown("### 🗣️ Ready to Chat?")
        if st.button("💬 Go to Chat", type="primary"):
            st.switch_page("pages/web_chat.py")
        
        return
    
    # Login/Register tabs
    tab1, tab2 = st.tabs(["🔐 Login", "📝 Register"])
    
    with tab1:
        st.header("Login to Your Account")
        
        with st.form("login_form"):
            email = st.text_input("Email", placeholder="your.email@example.com")
            password = st.text_input("Password", type="password")
            submit_login = st.form_submit_button("Login", type="primary")
            
            if submit_login:
                if not email or not password:
                    st.error("Please fill in all fields")
                else:
                    with st.spinner("Logging in..."):
                        result = login_user(email, password)
                        
                        if "error" in result:
                            st.error(f"❌ {result['error']}")
                        else:
                            st.session_state.token = result["access_token"]
                            st.success("✅ Login successful!")
                            st.rerun()
    
    with tab2:
        st.header("Create New Account")
        
        with st.form("register_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                email = st.text_input("Email *", placeholder="your.email@example.com")
                first_name = st.text_input("First Name", placeholder="Your first name")
                last_name = st.text_input("Last Name", placeholder="Your last name")
                display_name = st.text_input("Display Name", placeholder="How you'd like to be called")
            
            with col2:
                password = st.text_input("Password *", type="password", help="Must contain uppercase, lowercase, number, and special character")
                confirm_password = st.text_input("Confirm Password *", type="password")
                phone_number = st.text_input("Phone Number", placeholder="+1234567890")
                is_caregiver = st.checkbox("I am a caregiver", help="Check if you're caring for someone else")
            
            submit_register = st.form_submit_button("Register", type="primary")
            
            if submit_register:
                if not all([email, password, confirm_password]):
                    st.error("Please fill in all required fields (marked with *)")
                elif password != confirm_password:
                    st.error("Passwords do not match")
                else:
                    with st.spinner("Creating account..."):
                        result = register_user(
                            email=email,
                            password=password,
                            first_name=first_name if first_name else None,
                            last_name=last_name if last_name else None,
                            display_name=display_name if display_name else None,
                            phone_number=phone_number if phone_number else None,
                            is_caregiver=is_caregiver
                        )
                        
                        if "error" in result:
                            st.error(f"❌ {result['error']}")
                        else:
                            st.session_state.token = result["access_token"]
                            st.success("✅ Registration successful!")
                            st.rerun()
    
    # Password requirements
    st.markdown("---")
    st.markdown("### 🔒 Password Requirements")
    st.markdown("""
    - At least 8 characters long
    - Contains uppercase letter (A-Z)
    - Contains lowercase letter (a-z)
    - Contains number (0-9)
    - Contains special character (!@#$%^&*...)
    """)
    
    # Account information
    st.markdown("### 👤 Account Information")
    st.markdown("""
    - **Email**: Required for login and account recovery
    - **Display Name**: How you'll appear in the app (optional)
    - **Phone Number**: For additional verification (optional)
    - **Caregiver**: Check if you're caring for someone else's mental health
    """)

if __name__ == "__main__":
    main()
