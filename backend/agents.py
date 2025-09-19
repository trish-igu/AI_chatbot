"""
Multi-agent system for the conversational AI application.
Contains three specialized agents with distinct responsibilities.
"""

from typing import List, Dict, Any, Optional, Tuple
from openai import AsyncAzureOpenAI
from config import settings
import logging

logger = logging.getLogger(__name__)

# Shared Azure OpenAI client instance for efficiency
_azure_client: Optional[AsyncAzureOpenAI] = None

def get_azure_client() -> AsyncAzureOpenAI:
    """Get or create the shared Azure OpenAI client instance."""
    global _azure_client
    if _azure_client is None:
        _azure_client = AsyncAzureOpenAI(
            api_key=settings.azure_openai_api_key,
            api_version="2024-02-15-preview",
            azure_endpoint=settings.azure_openai_endpoint
        )
    return _azure_client

async def core_chat_agent(
    history: List[Dict[str, Any]],
    user_message: str,
    cumulative_context: str = None,
    suppress_greeting: bool = False,
    first_name: Optional[str] = None,
) -> Tuple[str, Dict[str, int], str]:
    """
    Core chat agent responsible for generating conversational replies with personal insights and HIPAA compliance.
    
    Args:
        history: List of previous conversation messages
        user_message: The user's current message
        cumulative_context: Context from all previous conversation summaries
        
    Returns:
        AI's conversational response
    """
    try:
        client = get_azure_client()
        
        # Prepare system prompt with HIPAA compliance and personal insights
        system_prompt = """You are Mindy, a warm and empathetic AI mental health assistant. Your role is to:

1. PERSONAL GREETING: Greet the user personally and warmly.
   - If prior conversation context is provided, show continuity and that you remember their journey.
   - If no prior context is provided, DO NOT claim to remember past chats; treat this as a first conversation.
2. SUPPORTIVE OBSERVATIONS: Provide gentle, supportive observations about patterns you notice in their emotional state and progress (only when grounded in provided context).
3. HIPAA COMPLIANCE: Never store, log, or reference specific personal identifiers. Focus on emotional patterns and general well-being trends.
4. SUPPORTIVE RESPONSES: Offer practical, evidence-based advice for mental health and happiness.
5. CONTINUITY: When prior context is available, reference it to show continuity of care and understanding.
6. CONTEXT AWARENESS: When history is available, use key events and relevant factors to provide personalized care. Pay close attention to the timestamps provided with each message (e.g., [YYYY-MM-DD HH:MM]) to understand the timeline of events. Prioritize the most recent messages for questions about recent events (e.g., 'yesterday').

MEMORY USAGE:
- The 'history' contains the immediate, ongoing conversation. Use it for high-fidelity, short-term recall.
- The 'Previous conversation context' is a summary of past conversations. Use it to understand long-term patterns, themes, and the user's overall journey.
- If there's a conflict between the immediate history and the long-term context, give more weight to the immediate history for recent events.

STYLE AND LENGTH:
- Be clear and easy to skim.
- Aim for 4–6 concise sentences (up to ~220 words) with a therapist-like tone.
- Use reflective listening, validation, and at least one open-ended question.
- Offer 1–2 practical coping tools or next steps when appropriate.
- Avoid unnecessary pleasantries; focus on supportive, clinical warmth.

IMPORTANT HIPAA GUIDELINES:
- Never ask for or reference specific personal information (names, addresses, SSNs, etc.).
- Focus on emotional and mental health patterns, not personal details.
- Maintain therapeutic boundaries while being warm and supportive.
- If you notice concerning patterns, gently suggest professional help without diagnosing.

CONTEXT USAGE:
- You will receive a system message titled "Previous conversation context" when history is available.
- If and only if that context is provided, reference relevant details from it to personalize your response.
- If no such context is provided, do not imply memory or prior interactions.

Be warm, encouraging, and show genuine care for their well-being while maintaining appropriate professional boundaries."""

        # Prepare messages for the API
        messages = [
            {
                "role": "system",
                "content": system_prompt
            }
        ]
        
        # Add cumulative context if available
        if cumulative_context and cumulative_context != "No previous conversation history available.":
            messages.append({
                "role": "system",
                "content": f"Previous conversation context:\n{cumulative_context}\n\nUse this context to provide personalized, continuous care while maintaining HIPAA compliance."
            })
        else:
            # Explicitly inform the model that there is no prior context, to prevent false memory claims.
            messages.append({
                "role": "system",
                "content": "No prior conversation context is available. Do not claim to remember previous chats. Treat this as the first conversation."
            })

        # Suppress greeting if requested to avoid double greetings when another component greets
        if suppress_greeting:
            messages.append({
                "role": "system",
                "content": "Do not include any greeting or pleasantries. Respond directly to the user's message in 3–6 sentences. Use reflective listening, validation, and a supportive, therapist-like tone. Ask one gentle, open-ended question and, if helpful, offer 1–2 practical coping steps."
            })
        else:
            # When not suppressed (e.g., first message in a conversation), ensure greeting starts with user's first name
            name_for_greeting = (first_name or "there").strip()
            messages.append({
                "role": "system",
                "content": f"Start your reply with: 'Hi {name_for_greeting},' then continue."
            })
        
        # Add conversation history
        messages.extend(history)
        
        # Add the current user message
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        response = await client.chat.completions.create(
            model=settings.azure_openai_deployment_name,
            messages=messages,
            temperature=0.6,
            max_tokens=350
        )
        
        text = response.choices[0].message.content.strip()
        # Azure responses include usage fields
        usage = {
            "prompt_tokens": getattr(getattr(response, "usage", None), "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(getattr(response, "usage", None), "completion_tokens", 0) or 0,
            "total_tokens": getattr(getattr(response, "usage", None), "total_tokens", 0) or 0,
        }
        model_name = getattr(response, "model", settings.azure_openai_deployment_name)
        return text, usage, model_name
        
    except Exception as e:
        logger.error(f"Error in core_chat_agent: {e}")
        
        # Handle content filter errors specifically
        if "content_filter" in str(e) or "ResponsibleAIPolicyViolation" in str(e):
            logger.warning("Content filter triggered - providing safe fallback response")
            return (
                "I understand you'd like to discuss something important. I'm here to support you with your mental health and well-being. Could you please rephrase your message in a way that focuses on your emotional state or concerns?",
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                settings.azure_openai_deployment_name,
            )
        
        return (
            "I'm sorry, I'm having trouble processing your message right now. Please try again.",
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            settings.azure_openai_deployment_name,
        )

async def summarizer_agent(conversation_history: List[Dict[str, Any]], cumulative_context: str = None) -> Tuple[str, Dict[str, int], str]:
    """
    Summarizer agent responsible for generating comprehensive conversation summaries with cumulative context.
    
    Args:
        conversation_history: Full conversation history to summarize
        cumulative_context: Context from all previous conversation summaries
        
    Returns:
        Comprehensive summary of the conversation
    """
    try:
        client = get_azure_client()
        
        # Prepare the conversation text for summarization
        conversation_text = ""
        for msg in conversation_history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, dict):
                content = content.get("text", str(content))
            conversation_text += f"{role}: {content}\n"
        
        system_prompt = """You are an expert mental health conversation summarizer. Create a comprehensive summary that captures:

1. CHRONOLOGICAL EMOTIONAL JOURNEY: Detail the user's emotional state in the order it evolved during the conversation (e.g., 'The user started by feeling sad about a friend leaving, but later in the conversation, they expressed happiness about a different friend's engagement.').
2. KEY TOPICS: Main themes, concerns, and situations discussed
3. PROGRESS INDICATORS: Any improvements, setbacks, or changes in their mental state
4. SUPPORT PROVIDED: Advice, strategies, or interventions discussed
5. PATTERNS: Any recurring themes or behaviors observed
6. KEY EVENTS: Important events, milestones, or significant moments mentioned
7. RELEVANT FACTORS: Contextual factors that influence the user's mental health (work, relationships, health, lifestyle, etc.)
8. HIPAA COMPLIANCE: Focus on emotional patterns, not personal identifiers

IMPORTANT: This summary will be part of a cumulative memory system. Each conversation builds upon previous ones to create a personalized care experience. Focus on:
- How this conversation relates to previous ones
- Any new developments or changes in the user's journey
- Patterns that continue or evolve from previous conversations
- Key events and relevant factors that provide context for future conversations
- Specific details that will help provide personalized care in future interactions

Create a detailed but concise summary (2-3 sentences, under 100 words) that will help provide personalized care in future conversations while maintaining privacy standards."""

        messages = [
            {
                "role": "system",
                "content": system_prompt
            }
        ]
        
        # Add cumulative context if available
        if cumulative_context and cumulative_context != "No previous conversation history available.":
            messages.append({
                "role": "system",
                "content": f"Previous conversation context to consider:\n{cumulative_context}\n\nUse this context to identify patterns and continuity in the user's mental health journey."
            })
        
        messages.append({
            "role": "user",
            "content": f"Please summarize this conversation:\n\n{conversation_text}"
        })
        
        response = await client.chat.completions.create(
            model=settings.azure_openai_deployment_name,
            messages=messages,
            temperature=0.3,
            max_tokens=150
        )
        
        text = response.choices[0].message.content.strip()
        usage = {
            "prompt_tokens": getattr(getattr(response, "usage", None), "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(getattr(response, "usage", None), "completion_tokens", 0) or 0,
            "total_tokens": getattr(getattr(response, "usage", None), "total_tokens", 0) or 0,
        }
        model_name = getattr(response, "model", settings.azure_openai_deployment_name)
        return text, usage, model_name
        
    except Exception as e:
        logger.error(f"Error in summarizer_agent: {e}")
        return (
            "Previous conversation about general topics",
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            settings.azure_openai_deployment_name,
        )

async def personalizer_agent(cumulative_context: str, first_name: Optional[str] = None) -> Tuple[str, Dict[str, int], str]:
    """
    Personalizer agent responsible for generating warm, welcoming greetings with cumulative context.
    
    Args:
        cumulative_context: Context from all previous conversation summaries
        
    Returns:
        Personalized greeting message
    """
    try:
        client = get_azure_client()
        
        system_prompt = """You are Mindy, a warm and caring AI mental health assistant. Create a personalized greeting that:

1. WELCOMES WARMTH: Greet the user back with genuine warmth and care
2. REFERENCES HISTORY: If prior conversation context is provided, reference specific details (feelings, situations, topics, progress). If no prior context is provided, DO NOT imply prior interactions.
3. SHOWS CONTINUITY: Only when history is available, demonstrate continuity and care about ongoing progress.
4. ASKS PROGRESS: Inquire how they're doing now in relation to what they've shared before
5. HIPAA COMPLIANCE: Focus on emotional patterns and general well-being, not personal identifiers
6. ENCOURAGING TONE: Be empathetic, supportive, and encouraging

IMPORTANT: Conversation history will be provided explicitly in the prompt when available.
- If "Previous conversation context" is provided, you may reference and build upon it.
- If it is not provided, treat this as a first-time greeting and avoid implying memory.

STYLE AND LENGTH:
- Keep it brief and pleasant: 1–2 short sentences (up to ~45 words).
- Start with the user's first name if provided.
- Do not add extra pleasantries beyond the greeting.

Make it feel personal, warm, and show genuine care for their mental health journey."""

        name_for_greeting = (first_name or "there").strip()
        messages = [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": f"Generate a warm, personalized greeting that begins with 'Hi {name_for_greeting},' for a user with this conversation history:\n\n{cumulative_context}"
            }
        ]
        
        response = await client.chat.completions.create(
            model=settings.azure_openai_deployment_name,
            messages=messages,
            temperature=0.8,
            max_tokens=200
        )
        
        text = response.choices[0].message.content.strip()
        usage = {
            "prompt_tokens": getattr(getattr(response, "usage", None), "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(getattr(response, "usage", None), "completion_tokens", 0) or 0,
            "total_tokens": getattr(getattr(response, "usage", None), "total_tokens", 0) or 0,
        }
        model_name = getattr(response, "model", settings.azure_openai_deployment_name)
        return text, usage, model_name
        
    except Exception as e:
        logger.error(f"Error in personalizer_agent: {e}")
        # Neutral, no-memory fallback to avoid false claims
        return (
            "Hi, I’m here for you. How can I support your well-being today?",
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            settings.azure_openai_deployment_name,
        )
