import React, { useState, useEffect } from "react";
import calService from "../../services/calService";
import { Clock, Calendar, CheckCircle2, ExternalLink, Loader2, ChevronRight, ChevronLeft } from "lucide-react";

/**
 * BookingSystem component for the User Chat
 * Shows available slots and allows booking with the assigned lawyer.
 */
export default function BookingSystem({ ticketId, onBookingComplete, theme = "dark", isSidebar = false }) {
  const isDark = theme === "dark";
  const [slots, setSlots] = useState({});
  const [loading, setLoading] = useState(true);
  const [bookingLoading, setBookingLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedDate, setSelectedDate] = useState(null);
  const [confirmation, setConfirmation] = useState(null);

  useEffect(() => {
    fetchSlots();
  }, [ticketId]);

  const fetchSlots = async () => {
    if (!ticketId) return;
    try {
      setLoading(true);
      setError(null);
      const data = await calService.getAvailableSlots(ticketId);
      const slotMap = data.slots || {};
      setSlots(slotMap);
      
      const dates = Object.keys(slotMap);
      if (dates.length > 0) {
        setSelectedDate(dates[0]);
      } else {
        setError("No available slots found for this lawyer.");
      }
    } catch (err) {
      console.error("❌ Failed to fetch slots:", err);
      const msg = err.message || "Failed to load available time slots.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleBook = async (startTime) => {
    try {
      setBookingLoading(true);
      const result = await calService.createBooking(ticketId, {
        start_time: startTime,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone
      });
      setConfirmation(result);
      if (onBookingComplete) onBookingComplete(result);
    } catch (err) {
      setError(err.message || "Failed to create booking.");
    } finally {
      setBookingLoading(false);
    }
  };

  if (loading) {
    return (
      <div className={`flex flex-col items-center justify-center ${isSidebar ? "p-4" : "p-8"} rounded-2xl border backdrop-blur-sm ${
        isDark ? "bg-white/5 border-white/10" : "bg-slate-50 border-slate-200"
      }`}>
        <Loader2 className="w-6 h-6 text-indigo-500 animate-spin mb-3" />
        <p className={`text-[10px] font-black uppercase tracking-widest ${isDark ? "text-slate-400" : "text-slate-500"}`}>Fetching slots...</p>
      </div>
    );
  }

  if (confirmation) {
    return (
      <div className={`${isSidebar ? "p-4" : "p-8"} rounded-2xl border backdrop-blur-sm text-center ${
        isDark ? "bg-emerald-500/10 border-emerald-500/20" : "bg-emerald-50 border-emerald-100"
      }`}>
        <div className="w-10 h-10 bg-emerald-500 rounded-xl flex items-center justify-center mx-auto mb-3 shadow-lg shadow-emerald-500/20">
          <CheckCircle2 className="text-white w-5 h-5" />
        </div>
        <h3 className={`${isSidebar ? "text-sm" : "text-lg"} font-black tracking-tight mb-2 ${isDark ? "text-white" : "text-slate-900"}`}>Booking Confirmed!</h3>
        <p className={`${isSidebar ? "text-[10px]" : "text-sm"} mb-4 font-medium ${isDark ? "text-emerald-400/80" : "text-emerald-600/80"}`}>
          Your meeting is scheduled. Check your email for details.
        </p>
      </div>
    );
  }

  const dates = Object.keys(slots);

  return (
    <div className={`flex flex-col rounded-2xl border shadow-xl overflow-hidden w-full ${
      isDark ? "bg-slate-900 border-white/10" : "bg-white border-slate-200"
    }`}>
      <div className={`${isSidebar ? "p-4" : "p-6"} border-b ${isDark ? "border-white/5 bg-white/5" : "border-slate-100 bg-slate-50/50"}`}>
        <div className="flex items-center gap-3">
          <h3 className={`text-xs font-black tracking-tight ${isDark ? "text-white" : "text-slate-900"}`}>Schedule Consultation</h3>
        </div>
      </div>

      {error && (
        <div className="p-3 bg-red-50 border-b border-red-100 text-red-600 text-[10px] font-bold text-center">
          {error}
        </div>
      )}

      {/* Date Selector */}
      <div className={`p-3 border-b overflow-x-auto flex gap-2 custom-scrollbar ${isDark ? "border-white/5" : "border-slate-100"}`}>
        {dates.map(date => {
          const d = new Date(date);
          const isSelected = selectedDate === date;
          return (
            <button
              key={date}
              onClick={() => setSelectedDate(date)}
              className={`flex-shrink-0 flex flex-col items-center justify-center w-14 h-16 rounded-xl border transition-all ${
                isSelected 
                  ? "bg-indigo-600 border-indigo-600 text-white shadow-lg shadow-indigo-500/30" 
                  : `${isDark ? "bg-slate-800 border-white/10 text-slate-400 hover:border-white/20" : "bg-white border-slate-200 text-slate-600 hover:border-indigo-300"}`
              }`}
            >
              <span className={`text-[8px] font-black uppercase tracking-tighter ${isSelected ? "text-indigo-100" : "text-slate-400"}`}>
                {d.toLocaleDateString('en-GB', { month: 'short' })}
              </span>
              <span className={`text-lg font-black ${isSelected ? "text-white" : (isDark ? "text-slate-200" : "text-slate-900")}`}>{d.getDate()}</span>
              <span className={`text-[8px] font-bold ${isSelected ? "text-indigo-100" : "text-slate-500"}`}>
                {d.toLocaleDateString('en-GB', { weekday: 'short' })}
              </span>
            </button>
          );
        })}
      </div>

      {/* Time Slots */}
      <div className={`${isSidebar ? "p-4" : "p-6"} max-h-[250px] overflow-y-auto custom-scrollbar`}>
        {selectedDate && slots[selectedDate] ? (
          <div className={`grid ${isSidebar ? "grid-cols-1" : "grid-cols-2"} gap-2`}>
            {slots[selectedDate].map((slot, idx) => {
              const timeStr = new Date(slot.time).toLocaleTimeString('en-GB', {
                hour: '2-digit',
                minute: '2-digit',
                hour12: false
              });
              return (
                <button
                  key={idx}
                  onClick={() => handleBook(slot.time)}
                  disabled={bookingLoading}
                  className={`flex items-center justify-between px-3 py-2.5 rounded-xl border transition-all group disabled:opacity-50 ${
                    isDark ? "bg-white/5 border-white/5 hover:bg-white/10" : "bg-slate-50 border-slate-100 hover:bg-indigo-50 hover:border-indigo-100"
                  }`}
                >
                  <span className={`text-xs font-bold ${isDark ? "text-slate-300 group-hover:text-white" : "text-slate-700 group-hover:text-indigo-600"}`}>{timeStr}</span>
                  <ChevronRight className={`w-3.5 h-3.5 transition-all ${isDark ? "text-slate-600 group-hover:text-slate-400" : "text-slate-300 group-hover:text-indigo-400"} group-hover:translate-x-0.5`} />
                </button>
              );
            })}
          </div>
        ) : (
          <div className="text-center py-6">
            <Clock className="w-6 h-6 text-slate-200 mx-auto mb-2" />
            <p className="text-[9px] font-black uppercase tracking-widest text-slate-400 italic">No slots available</p>
          </div>
        )}
      </div>

      {bookingLoading && (
        <div className={`absolute inset-0 backdrop-blur-[2px] flex flex-col items-center justify-center z-10 ${
          isDark ? "bg-slate-900/80" : "bg-white/80"
        }`}>
          <Loader2 className="w-6 h-6 text-indigo-600 animate-spin mb-2" />
          <p className="text-[10px] font-black uppercase tracking-widest text-indigo-600">Booking...</p>
        </div>
      )}
    </div>
  );
}
