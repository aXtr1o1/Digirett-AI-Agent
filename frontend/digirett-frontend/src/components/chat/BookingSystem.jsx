import React, { useState, useEffect } from "react";
import calService from "../../services/calService";
import { Clock, Calendar, CheckCircle2, ExternalLink, Loader2, ChevronRight, ChevronLeft } from "lucide-react";

/**
 * BookingSystem component for the User Chat
 * Shows available slots and allows booking with the assigned lawyer.
 */
export default function BookingSystem({ ticketId, onBookingComplete }) {
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
    try {
      setLoading(true);
      const data = await calService.getAvailableSlots(ticketId);
      setSlots(data.slots || {});
      
      // Auto-select first date with slots
      const dates = Object.keys(data.slots || {});
      if (dates.length > 0) {
        setSelectedDate(dates[0]);
      }
    } catch (err) {
      setError("Failed to load available time slots.");
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
      setError(err.response?.data?.detail || "Failed to create booking.");
    } finally {
      setBookingLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center p-8 bg-white/5 rounded-3xl border border-white/10 backdrop-blur-sm">
        <Loader2 className="w-8 h-8 text-indigo-500 animate-spin mb-4" />
        <p className="text-xs font-black uppercase tracking-widest text-slate-500">Fetching available slots...</p>
      </div>
    );
  }

  if (confirmation) {
    return (
      <div className="p-8 bg-emerald-500/10 rounded-3xl border border-emerald-500/20 backdrop-blur-sm text-center">
        <div className="w-12 h-12 bg-emerald-500 rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-lg shadow-emerald-500/20">
          <CheckCircle2 className="text-white w-6 h-6" />
        </div>
        <h3 className="text-lg font-black tracking-tight text-white mb-2">Booking Confirmed!</h3>
        <p className="text-sm text-emerald-400/80 mb-6 font-medium">
          Your meeting is scheduled for {new Date(confirmation.start_time).toLocaleString()}.
          Check your email for the calendar invitation and meeting link.
        </p>
        <div className="flex flex-col gap-3">
          <div className="p-4 bg-white/5 rounded-2xl border border-white/10 text-left">
            <div className="flex justify-between items-center text-[10px] font-black uppercase tracking-widest text-slate-500 mb-1">
              <span>Status</span>
              <span className="text-emerald-500">Confirmed</span>
            </div>
            <div className="text-sm font-bold text-white">Legal Consultation</div>
          </div>
        </div>
      </div>
    );
  }

  const dates = Object.keys(slots);

  return (
    <div className="flex flex-col bg-white rounded-3xl border border-slate-200 shadow-xl overflow-hidden max-w-md mx-auto">
      <div className="p-6 border-b border-slate-100 bg-slate-50/50">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-8 h-8 bg-indigo-600 rounded-xl flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <Calendar className="text-white w-4 h-4" />
          </div>
          <h3 className="font-black tracking-tight text-slate-900">Schedule Consultation</h3>
        </div>
        <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Select a convenient time slot</p>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border-b border-red-100 text-red-600 text-xs font-bold text-center">
          {error}
        </div>
      )}

      {/* Date Selector */}
      <div className="p-4 border-b border-slate-100 overflow-x-auto flex gap-2 custom-scrollbar">
        {dates.map(date => {
          const d = new Date(date);
          const isSelected = selectedDate === date;
          return (
            <button
              key={date}
              onClick={() => setSelectedDate(date)}
              className={`flex-shrink-0 flex flex-col items-center justify-center w-16 h-20 rounded-2xl border transition-all ${
                isSelected 
                  ? "bg-indigo-600 border-indigo-600 text-white shadow-lg shadow-indigo-500/30" 
                  : "bg-white border-slate-200 text-slate-600 hover:border-indigo-300"
              }`}
            >
              <span className={`text-[10px] font-black uppercase tracking-tighter ${isSelected ? "text-indigo-100" : "text-slate-400"}`}>
                {d.toLocaleDateString('en-GB', { month: 'short' })}
              </span>
              <span className="text-xl font-black">{d.getDate()}</span>
              <span className={`text-[9px] font-bold ${isSelected ? "text-indigo-100" : "text-slate-500"}`}>
                {d.toLocaleDateString('en-GB', { weekday: 'short' })}
              </span>
            </button>
          );
        })}
      </div>

      {/* Time Slots */}
      <div className="p-6 max-h-[300px] overflow-y-auto custom-scrollbar">
        {selectedDate && slots[selectedDate] ? (
          <div className="grid grid-cols-2 gap-3">
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
                  className="flex items-center justify-between px-4 py-3 bg-slate-50 border border-slate-100 rounded-2xl hover:bg-indigo-50 hover:border-indigo-100 transition-all group disabled:opacity-50"
                >
                  <span className="text-sm font-bold text-slate-700 group-hover:text-indigo-600">{timeStr}</span>
                  <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-indigo-400 group-hover:translate-x-0.5 transition-all" />
                </button>
              );
            })}
          </div>
        ) : (
          <div className="text-center py-8">
            <Clock className="w-8 h-8 text-slate-200 mx-auto mb-2" />
            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 italic">No slots available for this date</p>
          </div>
        )}
      </div>

      {bookingLoading && (
        <div className="absolute inset-0 bg-white/80 backdrop-blur-[2px] flex flex-col items-center justify-center z-10">
          <Loader2 className="w-8 h-8 text-indigo-600 animate-spin mb-4" />
          <p className="text-xs font-black uppercase tracking-widest text-indigo-600">Creating your booking...</p>
        </div>
      )}
    </div>
  );
}
