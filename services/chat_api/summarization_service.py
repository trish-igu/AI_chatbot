"""
Background summarization service for the hybrid approach.
Processes conversations that have been inactive for a configurable period.
"""

import asyncio
import logging
from sqlalchemy.ext.asyncio import AsyncSession

# Local application imports
from database import async_session_maker, init_database
from crud import (
    get_conversations_to_summarize,
    get_message_history,
    update_conversation_summary,
    get_cumulative_summary_context,
    update_conversation_status,
    get_conversations_to_archive
)
from agents import summarizer_agent
from config import settings

logger = logging.getLogger(__name__)

class SummarizationService:
    """Service to handle background conversation summarization."""
    
    def __init__(self):
        self.running = False
        # Make the check interval configurable via settings
        self.check_interval = settings.summarization_interval_seconds

    async def start(self):
        """Start the background summarization service."""
        logger.info(f"Starting background summarization service. Check interval: {self.check_interval} seconds.")
        logger.info("Service will only process conversations when they become inactive (15+ minutes without messages)")
        
        # Initialize database for this service
        logger.info("Initializing database for summarization service...")
        await init_database(settings.database_url)
        logger.info("Database initialized successfully for summarization service")
        
        self.running = True
        
        while self.running:  
            try:
                await self.process_pending_summaries()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                logger.info("Summarization service task was cancelled.")
                break
            except Exception as e:
                logger.error(f"Error in summarization service main loop: {e}", exc_info=True)
                await asyncio.sleep(60) # Wait 1 minute before retrying after a major loop error

    async def stop(self):
        """Stop the background summarization service."""
        logger.info("Stopping background summarization service...")
        self.running = False
        # Close database connection
        from database import close_database
        await close_database()

    async def process_pending_summaries(self):
        """Process conversations that need archiving and immediate summarization."""
        try:
            # Use the service's own database connection
            from database import async_session_maker as service_session_maker
            
            async with service_session_maker() as db:
                # Find conversations that need to be archived (inactive for 15+ minutes)
                conversations_to_archive = await get_conversations_to_archive(db)
                
                if not conversations_to_archive:
                    # Only log debug message - this is normal when no conversations need processing
                    logger.debug("No conversations need archiving - this is normal when no active conversations exist or all conversations are already processed")
                    return
                
                logger.info(f"Starting summarization service cycle - found {len(conversations_to_archive)} conversations to process")
                
                successful_summaries = 0
                failed_summaries = 0
                
                for conversation in conversations_to_archive:
                    try:
                        logger.info(f"Processing conversation {conversation.conversation_id} (last message: {conversation.last_message_at})")
                        
                        # Step 1: Archive the conversation
                        await update_conversation_status(db, conversation.conversation_id, "archived")
                        logger.info(f"Archived conversation {conversation.conversation_id}")
                        
                        # Step 2: Immediately summarize the archived conversation
                        await self.summarize_conversation(db, conversation)
                        successful_summaries += 1
                        
                        logger.info(f"Successfully archived and summarized conversation {conversation.conversation_id}")
                        
                    except Exception as e:
                        logger.error(f"Failed to process conversation {conversation.conversation_id}: {e}")
                        failed_summaries += 1
                        continue
                
                logger.info(f"Archiving and summarization cycle complete: {successful_summaries} successful, {failed_summaries} failed")
                
        except Exception as e:
            logger.error(f"Error processing pending summaries: {e}")

    async def summarize_conversation(self, db: AsyncSession, conversation):
        """Summarize a single conversation, handling its own transaction."""
        conversation_id = conversation.conversation_id
        user_id = conversation.user_id
        
        try:
            messages = await get_message_history(db, conversation_id)
            if len(messages) < 2:
                logger.warning(f"Skipping conversation {conversation_id}: insufficient messages for a meaningful summary.")
                # Update status to archived to prevent reprocessing
                await update_conversation_status(db, conversation_id, "archived")
                await db.commit()
                return

            cumulative_context = await get_cumulative_summary_context(db, user_id)
            
            formatted_messages = [
                {"role": msg.role, "content": msg.content.get("text", str(msg.content))}
                for msg in messages
            ]
            
            logger.info(f"Generating summary for conversation {conversation_id}...")
            summary, usage, model_name = await summarizer_agent(formatted_messages, cumulative_context)
            
            await update_conversation_summary(db, conversation_id, summary, model=model_name, token_usage=usage)
            logger.info(f"Successfully summarized conversation {conversation_id}.")
            
            # Commit this individual summary immediately.
            await db.commit()
            
        except Exception as e:
            logger.error(f"Failed to summarize conversation {conversation_id} within its transaction: {e}")
            # Rollback this specific conversation's changes to leave it in its original state for the next run.
            await db.rollback()
            raise # Re-raise the exception to be caught by the main processing loop for counting failures

# --- Service Management ---

summarization_service = SummarizationService()

async def start_summarization_service():
    """Entry point to start the background summarization service."""
    await summarization_service.start()

async def stop_summarization_service():
    """Entry point to stop the background summarization service."""
    await summarization_service.stop()

if __name__ == "__main__":
    # Allows the service to be run standalone for testing or as a separate process.
    async def main():
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        try:
            logger.info("Running summarization service in standalone mode...")
            await start_summarization_service()
        except KeyboardInterrupt:
            logger.info("Interrupt signal received, shutting down.")
        finally:
            await stop_summarization_service()
    
    asyncio.run(main())


