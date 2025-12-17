"""
Database Manager for Supabase operations
Handles session and event persistence
"""
from datetime import datetime
from typing import Dict, List, Optional, Any
from supabase import Client


class DatabaseManager:
    """Manages all database operations for sessions and events"""
    
    def __init__(self, supabase_client: Client):
        self.supabase = supabase_client
    
    async def create_session(self, session_id: str, user_id: str) -> Dict:
        """
        Create a new session record
        
        Args:
            session_id: Unique session identifier
            user_id: User identifier
            
        Returns:
            Created session data
        """
        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "start_time": datetime.utcnow().isoformat(),
            "end_time": None,
            "duration_seconds": None,
            "summary": None,
            "status": "active"
        }
        
        try:
            response = self.supabase.table("sessions").insert(session_data).execute()
            print(f"✓ Session created: {session_id}")
            return session_data
        except Exception as e:
            print(f"Error creating session: {e}")
            raise
    
    async def end_session(self, session_id: str) -> Dict:
        """
        Update session with end time and calculate duration
        
        Args:
            session_id: Session identifier
            
        Returns:
            Updated session data
        """
        try:
            # Get session start time
            response = self.supabase.table("sessions").select("start_time").eq("session_id", session_id).execute()
            
            if not response.data:
                raise ValueError(f"Session {session_id} not found")
            
            start_time = datetime.fromisoformat(response.data[0]["start_time"])
            end_time = datetime.utcnow()
            duration = int((end_time - start_time).total_seconds())
            
            # Update session
            update_data = {
                "end_time": end_time.isoformat(),
                "duration_seconds": duration,
                "status": "completed"
            }
            
            response = self.supabase.table("sessions").update(update_data).eq("session_id", session_id).execute()
            
            print(f"✓ Session ended: {session_id}, duration: {duration}s")
            return response.data[0] if response.data else {}
        
        except Exception as e:
            print(f"Error ending session: {e}")
            raise
    
    async def update_session_summary(self, session_id: str, summary: str) -> Dict:
        """
        Update session with generated summary
        
        Args:
            session_id: Session identifier
            summary: Generated summary text
            
        Returns:
            Updated session data
        """
        try:
            update_data = {
                "summary": summary,
                "status": "summarized"
            }
            
            response = self.supabase.table("sessions").update(update_data).eq("session_id", session_id).execute()
            
            print(f"✓ Session summary saved: {session_id}")
            return response.data[0] if response.data else {}
        
        except Exception as e:
            print(f"Error updating session summary: {e}")
            raise
    
    async def log_event(
        self,
        session_id: str,
        event_type: str,
        data: Dict[str, Any],
        metadata: Optional[Dict] = None
    ) -> Dict:
        """
        Log an event in the session event log
        
        Args:
            session_id: Session identifier
            event_type: Type of event (user_message, assistant_response, etc.)
            data: Event data payload
            metadata: Optional additional metadata
            
        Returns:
            Created event record
        """
        event_data = {
            "session_id": session_id,
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data,
            "metadata": metadata or {}
        }
        
        try:
            response = self.supabase.table("session_events").insert(event_data).execute()
            return response.data[0] if response.data else {}
        
        except Exception as e:
            print(f"Error logging event: {e}")
            # Don't raise - logging errors shouldn't break the application
            return {}
    
    async def get_session_events(
        self,
        session_id: str,
        event_types: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Retrieve events for a session
        
        Args:
            session_id: Session identifier
            event_types: Optional filter for specific event types
            
        Returns:
            List of event records ordered by timestamp
        """
        try:
            query = self.supabase.table("session_events").select("*").eq("session_id", session_id)
            
            if event_types:
                query = query.in_("event_type", event_types)
            
            response = query.order("timestamp", desc=False).execute()
            
            return response.data or []
        
        except Exception as e:
            print(f"Error retrieving session events: {e}")
            return []
    
    async def get_session(self, session_id: str) -> Optional[Dict]:
        """
        Retrieve session data
        
        Args:
            session_id: Session identifier
            
        Returns:
            Session record or None
        """
        try:
            response = self.supabase.table("sessions").select("*").eq("session_id", session_id).execute()
            
            return response.data[0] if response.data else None
        
        except Exception as e:
            print(f"Error retrieving session: {e}")
            return None
    
    async def get_conversation_history(self, session_id: str) -> List[Dict]:
        """
        Get formatted conversation history from events
        
        Args:
            session_id: Session identifier
            
        Returns:
            List of conversation messages
        """
        events = await self.get_session_events(
            session_id,
            event_types=["user_message", "assistant_response"]
        )
        
        conversation = []
        for event in events:
            if event["event_type"] == "user_message":
                conversation.append({
                    "role": "user",
                    "content": event["data"].get("content", ""),
                    "timestamp": event["timestamp"]
                })
            elif event["event_type"] == "assistant_response":
                conversation.append({
                    "role": "assistant",
                    "content": event["data"].get("content", ""),
                    "timestamp": event["timestamp"]
                })
        
        return conversation
    
    async def get_recent_sessions(self, user_id: str, limit: int = 10) -> List[Dict]:
        """
        Get recent sessions for a user
        
        Args:
            user_id: User identifier
            limit: Maximum number of sessions to return
            
        Returns:
            List of session records
        """
        try:
            response = (
                self.supabase.table("sessions")
                .select("*")
                .eq("user_id", user_id)
                .order("start_time", desc=True)
                .limit(limit)
                .execute()
            )
            
            return response.data or []
        
        except Exception as e:
            print(f"Error retrieving recent sessions: {e}")
            return []
    
    async def get_session_statistics(self, session_id: str) -> Dict:
        """
        Calculate statistics for a session
        
        Args:
            session_id: Session identifier
            
        Returns:
            Dictionary with session statistics
        """
        try:
            events = await self.get_session_events(session_id)
            
            stats = {
                "total_events": len(events),
                "user_messages": sum(1 for e in events if e["event_type"] == "user_message"),
                "assistant_responses": sum(1 for e in events if e["event_type"] == "assistant_response"),
                "function_calls": sum(1 for e in events if e["event_type"] == "function_call"),
                "event_types": {}
            }
            
            # Count event types
            for event in events:
                event_type = event["event_type"]
                stats["event_types"][event_type] = stats["event_types"].get(event_type, 0) + 1
            
            return stats
        
        except Exception as e:
            print(f"Error calculating session statistics: {e}")
            return {}
    
    async def delete_session(self, session_id: str) -> bool:
        """
        Delete a session and all its events
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if successful
        """
        try:
            # Delete events first (due to foreign key constraint)
            self.supabase.table("session_events").delete().eq("session_id", session_id).execute()
            
            # Delete session
            self.supabase.table("sessions").delete().eq("session_id", session_id).execute()
            
            print(f"✓ Session deleted: {session_id}")
            return True
        
        except Exception as e:
            print(f"Error deleting session: {e}")
            return False