"""
Session Processor for post-session analysis and summarization
Runs asynchronously after session ends
"""
import asyncio
from typing import Dict, List
from datetime import datetime
import anthropic
from supabase import Client

from database import DatabaseManager


class SessionProcessor:
    """Handles post-session processing including summary generation"""
    
    def __init__(self, supabase_client: Client, anthropic_api_key: str):
        self.supabase = supabase_client
        self.db_manager = DatabaseManager(supabase_client)
        self.anthropic_client = anthropic.Anthropic(api_key=anthropic_api_key)
    
    async def process_session(self, session_id: str):
        """
        Main processing function called after session ends
        
        Args:
            session_id: Session identifier
        """
        print(f"Starting post-session processing for {session_id}")
        
        try:
            # Small delay to ensure all data is committed
            await asyncio.sleep(1)
            
            # Get session data
            session = await self.db_manager.get_session(session_id)
            if not session:
                print(f"Session {session_id} not found")
                return
            
            # Get conversation history
            conversation = await self.db_manager.get_conversation_history(session_id)
            
            if not conversation:
                print(f"No conversation history for session {session_id}")
                summary = "No conversation data available for this session."
            else:
                # Generate summary using LLM
                summary = await self.generate_summary(conversation, session)
            
            # Update session with summary
            await self.db_manager.update_session_summary(session_id, summary)
            
            # Get and log statistics
            stats = await self.db_manager.get_session_statistics(session_id)
            
            # Log processing completion
            await self.db_manager.log_event(
                session_id=session_id,
                event_type="post_processing_complete",
                data={
                    "summary_generated": True,
                    "summary_length": len(summary),
                    "statistics": stats
                }
            )
            
            print(f"✓ Post-session processing complete for {session_id}")
            print(f"  - Messages: {stats.get('user_messages', 0)} user, {stats.get('assistant_responses', 0)} assistant")
            print(f"  - Function calls: {stats.get('function_calls', 0)}")
            print(f"  - Summary: {len(summary)} characters")
        
        except Exception as e:
            print(f"Error in post-session processing: {e}")
            
            # Log the error
            try:
                await self.db_manager.log_event(
                    session_id=session_id,
                    event_type="post_processing_error",
                    data={"error": str(e)}
                )
            except:
                pass
    
    async def generate_summary(self, conversation: List[Dict], session: Dict) -> str:
        """
        Generate a concise summary of the conversation using LLM
        
        Args:
            conversation: List of conversation messages
            session: Session metadata
            
        Returns:
            Generated summary text
        """
        try:
            # Format conversation for analysis
            conversation_text = self._format_conversation(conversation)
            
            # Calculate session duration
            duration = session.get("duration_seconds", 0)
            duration_str = self._format_duration(duration)
            
            # Prepare prompt for summary
            prompt = f"""Analyze the following conversation and provide a concise summary.

Session Information:
- Session ID: {session['session_id']}
- Duration: {duration_str}
- User ID: {session['user_id']}

Conversation:
{conversation_text}

Please provide:
1. A brief overview (2-3 sentences) of what was discussed
2. Key topics or themes
3. Any actions taken or tools used
4. Overall sentiment and engagement level

Keep the summary concise and informative."""

            # Call Claude API for summary generation
            message = self.anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            # Extract summary from response
            summary = message.content[0].text
            
            return summary
        
        except Exception as e:
            print(f"Error generating summary: {e}")
            return f"Error generating summary: {str(e)}"
    
    def _format_conversation(self, conversation: List[Dict]) -> str:
        """
        Format conversation history into readable text
        
        Args:
            conversation: List of conversation messages
            
        Returns:
            Formatted conversation string
        """
        formatted = []
        
        for msg in conversation:
            role = msg["role"].upper()
            content = msg["content"]
            timestamp = msg.get("timestamp", "")
            
            formatted.append(f"[{timestamp}] {role}: {content}")
        
        return "\n".join(formatted)
    
    def _format_duration(self, seconds: int) -> str:
        """
        Format duration in seconds to human-readable string
        
        Args:
            seconds: Duration in seconds
            
        Returns:
            Formatted duration string
        """
        if seconds < 60:
            return f"{seconds} seconds"
        elif seconds < 3600:
            minutes = seconds // 60
            secs = seconds % 60
            return f"{minutes} minutes, {secs} seconds"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours} hours, {minutes} minutes"
    
    async def analyze_session_patterns(self, user_id: str, limit: int = 5) -> Dict:
        """
        Analyze patterns across multiple sessions for a user
        
        Args:
            user_id: User identifier
            limit: Number of recent sessions to analyze
            
        Returns:
            Dictionary with pattern analysis
        """
        try:
            # Get recent sessions
            sessions = await self.db_manager.get_recent_sessions(user_id, limit)
            
            if not sessions:
                return {"error": "No sessions found for user"}
            
            # Aggregate statistics
            total_duration = sum(s.get("duration_seconds", 0) for s in sessions)
            avg_duration = total_duration / len(sessions)
            
            # Get all events for these sessions
            all_stats = []
            for session in sessions:
                stats = await self.db_manager.get_session_statistics(session["session_id"])
                all_stats.append(stats)
            
            # Calculate averages
            avg_messages = sum(s.get("user_messages", 0) for s in all_stats) / len(all_stats)
            avg_responses = sum(s.get("assistant_responses", 0) for s in all_stats) / len(all_stats)
            total_functions = sum(s.get("function_calls", 0) for s in all_stats)
            
            analysis = {
                "user_id": user_id,
                "sessions_analyzed": len(sessions),
                "total_duration_seconds": total_duration,
                "average_duration_seconds": avg_duration,
                "average_user_messages": avg_messages,
                "average_assistant_responses": avg_responses,
                "total_function_calls": total_functions,
                "most_recent_session": sessions[0]["session_id"] if sessions else None
            }
            
            return analysis
        
        except Exception as e:
            print(f"Error analyzing session patterns: {e}")
            return {"error": str(e)}
    
    async def generate_insights_report(self, session_id: str) -> Dict:
        """
        Generate detailed insights report for a session
        
        Args:
            session_id: Session identifier
            
        Returns:
            Dictionary with detailed insights
        """
        try:
            session = await self.db_manager.get_session(session_id)
            events = await self.db_manager.get_session_events(session_id)
            stats = await self.db_manager.get_session_statistics(session_id)
            
            # Analyze event timeline
            timeline = []
            for event in events:
                timeline.append({
                    "timestamp": event["timestamp"],
                    "event_type": event["event_type"],
                    "summary": self._summarize_event(event)
                })
            
            # Calculate engagement metrics
            response_times = []
            for i in range(len(events) - 1):
                if events[i]["event_type"] == "user_message" and events[i+1]["event_type"] == "assistant_response":
                    t1 = datetime.fromisoformat(events[i]["timestamp"])
                    t2 = datetime.fromisoformat(events[i+1]["timestamp"])
                    response_times.append((t2 - t1).total_seconds())
            
            avg_response_time = sum(response_times) / len(response_times) if response_times else 0
            
            insights = {
                "session_id": session_id,
                "session_summary": session.get("summary", "No summary available"),
                "statistics": stats,
                "timeline": timeline,
                "engagement_metrics": {
                    "average_response_time_seconds": avg_response_time,
                    "total_interactions": stats.get("user_messages", 0),
                    "tools_utilized": stats.get("function_calls", 0)
                }
            }
            
            return insights
        
        except Exception as e:
            print(f"Error generating insights report: {e}")
            return {"error": str(e)}
    
    def _summarize_event(self, event: Dict) -> str:
        """
        Create a brief summary of an event
        
        Args:
            event: Event record
            
        Returns:
            Brief summary string
        """
        event_type = event["event_type"]
        data = event.get("data", {})
        
        if event_type == "user_message":
            content = data.get("content", "")
            return f"User: {content[:50]}..." if len(content) > 50 else f"User: {content}"
        
        elif event_type == "assistant_response":
            content = data.get("content", "")
            return f"Assistant: {content[:50]}..." if len(content) > 50 else f"Assistant: {content}"
        
        elif event_type == "function_call":
            func_name = data.get("function_name", "unknown")
            return f"Called function: {func_name}"
        
        elif event_type == "function_result":
            func_name = data.get("function_name", "unknown")
            return f"Function {func_name} completed"
        
        else:
            return f"Event: {event_type}"