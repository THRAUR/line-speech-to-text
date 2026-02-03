"""Daily rotating password manager."""
from datetime import datetime, timezone, timedelta
from typing import Optional


class PasswordManager:
    """Manages daily rotating passwords and user sessions.
    
    Password format: 'meetingMMDD' (e.g., 'meeting0203' for Feb 3rd)
    Sessions are stored in memory and reset on server restart.
    """
    
    # Timezone for Taiwan (UTC+8)
    TW_TIMEZONE = timezone(timedelta(hours=8))
    
    def __init__(self, seed: str = "default"):
        """Initialize the password manager.
        
        Args:
            seed: Secret seed for password generation (not currently used,
                  but kept for future enhancement)
        """
        self._seed = seed
        # Store authenticated user IDs with their auth date
        # Format: {user_id: auth_date_string}
        self._authenticated_users: dict[str, str] = {}
    
    def get_today_password(self) -> str:
        """Generate today's password based on the date.
        
        Returns:
            Password string in format 'meetingMMDD'
        """
        now = datetime.now(self.TW_TIMEZONE)
        return f"meeting{now.month:02d}{now.day:02d}"
    
    def get_today_date_string(self) -> str:
        """Get today's date as a string for session tracking."""
        now = datetime.now(self.TW_TIMEZONE)
        return now.strftime("%Y-%m-%d")
    
    def check_password(self, password: str) -> bool:
        """Check if the provided password matches today's password.
        
        Args:
            password: Password to verify
            
        Returns:
            True if password matches, False otherwise
        """
        return password.strip().lower() == self.get_today_password().lower()
    
    def authenticate_user(self, user_id: str, password: str) -> tuple[bool, str]:
        """Attempt to authenticate a user with a password.
        
        Args:
            user_id: LINE user ID
            password: Password provided by user
            
        Returns:
            Tuple of (success, message)
        """
        if self.check_password(password):
            self._authenticated_users[user_id] = self.get_today_date_string()
            return True, "✅ Authentication successful! You can now send voice messages."
        return False, "❌ Incorrect password. Please try again."
    
    def is_authenticated(self, user_id: str) -> bool:
        """Check if a user is authenticated for today.
        
        Args:
            user_id: LINE user ID to check
            
        Returns:
            True if user is authenticated for today, False otherwise
        """
        auth_date = self._authenticated_users.get(user_id)
        if not auth_date:
            return False
        # Check if auth is still valid (same day)
        return auth_date == self.get_today_date_string()
    
    def get_unauthenticated_message(self) -> str:
        """Get the message to show unauthenticated users."""
        return (
            "🔐 Please enter today's password to use this bot.\n\n"
            "Format: meetingMMDD\n"
            "Example: meeting0203 (for Feb 3rd)"
        )
    
    def get_session_count(self) -> int:
        """Get the number of active sessions."""
        today = self.get_today_date_string()
        return sum(1 for date in self._authenticated_users.values() if date == today)
