# ============================================
# app/utils/metrics.py
# ============================================

import time
from collections import defaultdict
from typing import Dict, Any
import threading


class MetricsCollector:
    """Collect and track API metrics"""
    
    def __init__(self):
        self.start_time = time.time()
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.total_response_time = 0.0
        self.endpoint_stats = defaultdict(lambda: {
            "count": 0,
            "total_time": 0.0,
            "errors": 0
        })
        self.error_counts = defaultdict(int)
        self.feedback_ratings = []
        self.feedback_helpful = []
        
        self._lock = threading.Lock()
    
    def record_request(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        duration: float
    ):
        """Record a request"""
        with self._lock:
            self.total_requests += 1
            self.total_response_time += duration
            
            if 200 <= status_code < 300:
                self.successful_requests += 1
            else:
                self.failed_requests += 1
            
            self.endpoint_stats[endpoint]["count"] += 1
            self.endpoint_stats[endpoint]["total_time"] += duration
    
    def record_error(self, endpoint: str, error_type: str):
        """Record an error"""
        with self._lock:
            self.endpoint_stats[endpoint]["errors"] += 1
            self.error_counts[error_type] += 1
    
    def record_feedback(self, rating: int, helpful: bool):
        """Record user feedback"""
        with self._lock:
            self.feedback_ratings.append(rating)
            self.feedback_helpful.append(helpful)
    
    def get_total_queries(self) -> int:
        """Get total queries processed"""
        return self.total_requests
    
    def get_uptime(self) -> float:
        """Get uptime in seconds"""
        return time.time() - self.start_time
    
    def get_stats(self) -> Dict[str, Any]:
        """Get all statistics"""
        with self._lock:
            avg_response_time = (
                self.total_response_time / self.total_requests
                if self.total_requests > 0
                else 0.0
            )
            
            avg_rating = (
                sum(self.feedback_ratings) / len(self.feedback_ratings)
                if self.feedback_ratings
                else 0.0
            )
            
            helpful_percentage = (
                sum(self.feedback_helpful) / len(self.feedback_helpful) * 100
                if self.feedback_helpful
                else 0.0
            )
            
            return {
                "total_requests": self.total_requests,
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "success_rate": (
                    self.successful_requests / self.total_requests * 100
                    if self.total_requests > 0
                    else 0.0
                ),
                "average_response_time": round(avg_response_time, 3),
                "uptime_seconds": round(self.get_uptime(), 2),
                "endpoint_stats": dict(self.endpoint_stats),
                "error_counts": dict(self.error_counts),
                "feedback": {
                    "average_rating": round(avg_rating, 2),
                    "helpful_percentage": round(helpful_percentage, 1),
                    "total_feedback": len(self.feedback_ratings)
                }
            }