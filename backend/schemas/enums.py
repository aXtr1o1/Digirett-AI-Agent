from enum import Enum

class TicketStatus(str, Enum):
    OPEN = "open"
    ASSIGNED = "assigned"
    BOOKED = "booked"
    RESOLVED = "resolved"
    CLOSED = "closed"
