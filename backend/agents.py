"""
Multi-agent system for the conversational AI application.
Contains three specialized agents with distinct responsibilities.
"""

from typing import List, Dict, Any, Optional
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

async def core_chat_agent(history: List[Dict[str, Any]], user_message: str, cumulative_context: str = None) -> str:
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

1. PERSONAL GREETING: Always greet the user personally, referencing their previous conversations and showing you remember their journey
2. SUPPORTIVE OBSERVATIONS: Provide gentle, supportive observations about patterns you notice in their emotional state and progress
3. HIPAA COMPLIANCE: Never store, log, or reference specific personal identifiers. Focus on emotional patterns and general well-being trends
4. SUPPORTIVE RESPONSES: Offer practical, evidence-based advice for mental health and happiness
5. CONTINUITY: Reference their previous conversations to show continuity of care and understanding
6. CONTEXT AWARENESS: Use key events and relevant factors from their history to provide personalized care

IMPORTANT HIPAA GUIDELINES:
- Never ask for or reference specific personal information (names, addresses, SSNs, etc.)
- Focus on emotional and mental health patterns, not personal details
- Maintain therapeutic boundaries while being warm and supportive
- If you notice concerning patterns, gently suggest professional help without diagnosing

CONTEXT USAGE:
- Reference key events, milestones, or significant moments from their previous conversations
- Consider relevant factors like work situations, relationships, health, lifestyle changes
- Show that you remember important details that provide context for their current situation
- Use this cumulative memory to provide more personalized and relevant support

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
            temperature=0.7,
            max_tokens=500
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        logger.error(f"Error in core_chat_agent: {e}")
        
        # Handle content filter errors specifically
        if "content_filter" in str(e) or "ResponsibleAIPolicyViolation" in str(e):
            logger.warning("Content filter triggered - providing safe fallback response")
            return "I understand you'd like to discuss something important. I'm here to support you with your mental health and well-being. Could you please rephrase your message in a way that focuses on your emotional state or concerns?"
        
        return "I'm sorry, I'm having trouble processing your message right now. Please try again."

async def summarizer_agent(conversation_history: List[Dict[str, Any]], cumulative_context: str = None) -> str:
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

1. EMOTIONAL STATE: How the user was feeling throughout the conversation
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
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        logger.error(f"Error in summarizer_agent: {e}")
        return "Previous conversation about general topics"

async def personalizer_agent(cumulative_context: str) -> str:
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
2. REFERENCES HISTORY: Reference specific details from their previous conversations (feelings, situations, topics, progress)
3. SHOWS CONTINUITY: Demonstrate you remember their journey and care about their ongoing progress
4. ASKS PROGRESS: Inquire how they're doing now in relation to what they've shared before
5. HIPAA COMPLIANCE: Focus on emotional patterns and general well-being, not personal identifiers
6. ENCOURAGING TONE: Be empathetic, supportive, and encouraging

IMPORTANT: You have access to the user's complete conversation history. Use this cumulative memory to:
- Reference specific topics, feelings, or situations from previous conversations
- Show continuity in their mental health journey
- Ask about progress on things they've discussed before
- Demonstrate that you remember and care about their ongoing well-being
- Reference key events and relevant factors that provide context (work situations, relationships, health, lifestyle changes, etc.)
- Show that you remember important milestones, events, or significant moments they've shared

Make it feel personal, warm, and show genuine care for their mental health journey. Keep it to 2-3 sentences while maintaining appropriate professional boundaries."""

        messages = [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": f"Generate a warm, personalized greeting for a user with this conversation history:\n\n{cumulative_context}"
            }
        ]
        
        response = await client.chat.completions.create(
            model=settings.azure_openai_deployment_name,
            messages=messages,
            temperature=0.8,
            max_tokens=200
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        logger.error(f"Error in personalizer_agent: {e}")
        return "Welcome back! I'm glad to see you again. How can I help you feel happy today?"
