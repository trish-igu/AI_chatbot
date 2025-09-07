import streamlit as st
import requests
import uuid

# --- Page Configuration ---
st.set_page_config(
    page_title="Chat with Mindy",
    page_icon="😊",
    layout="centered"
)

# --- Backend API Configuration ---
BACKEND_URL = "http://127.0.0.1:8000/api/ai/chat"
# This is a placeholder token for development, matching the backend.
BEARER_TOKEN = "testtoken" 

# --- Session State Initialization ---
# This ensures that the conversation history and ID are preserved between reruns.
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- UI Rendering ---

# Header
st.title("I GET HAPPY 😊")
st.subheader("Chat with Mindy, your AI Assistant")

# Display the introductory message if the chat is new
if not st.session_state.messages:
    with st.chat_message("assistant", avatar="🤖"):
        st.write("Hello! I'm Mindy. How can I help you feel a little happier today?")

# Display existing chat messages from session state
for message in st.session_state.messages:
    with st.chat_message(message["role"], avatar="👤" if message["role"] == "user" else "🤖"):
        st.markdown(message["content"])

# --- Chat Input and API Call Logic ---

# Get user input from the chat box
if prompt := st.chat_input("What's on your mind?"):
    
    # 1. Add user message to session state and display it
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    # 2. Prepare for and make the API call to the backend
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Mindy is thinking..."):
            try:
                headers = {
                    "Authorization": f"Bearer {BEARER_TOKEN}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "conversation_id": st.session_state.conversation_id,
                    "message": prompt
                }

                response = requests.post(BACKEND_URL, headers=headers, json=payload)
                response.raise_for_status()  # This will raise an exception for 4xx or 5xx status codes

                data = response.json()
                ai_response = data["response"]
                
                # 3. Update conversation ID and display AI response
                st.session_state.conversation_id = data["conversation_id"]
                st.session_state.messages.append({"role": "assistant", "content": ai_response})
                st.write(ai_response)

            except requests.exceptions.RequestException as e:
                error_message = f"Sorry, I couldn't connect to the backend. Please make sure it's running. \n\n**Error:** `{e}`"
                st.session_state.messages.append({"role": "assistant", "content": error_message})
                st.error(error_message)

# ### How to Run Your New Frontend

# 1.  **Create a `frontend` folder** next to your `backend` folder to keep your project organized.
# 2.  **Save the code above** as a new file named `app.py` inside this `frontend` folder.
# 3.  **Ensure your backend is running:** You must have both the Cloud SQL Auth Proxy and the FastAPI server (`python main.py`) running in their own terminals.
# 4.  **Open a *third* terminal**, navigate into your project's main folder (`AI_chatbot`), and run the Streamlit app with the following command:

#     ```bash
#     streamlit run frontend/app.py
    
