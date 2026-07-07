import React, { useState, useEffect } from "react";
import { 
  ChevronLeft, 
  ChevronRight, 
  Video, 
  ExternalLink, 
  MessageSquare, 
  Clock, 
  User, 
  X, 
  Shield,
  Menu as MenuIcon,
  Calendar as CalIcon,
  ChevronDown
} from "lucide-react";
import { Link } from "react-router-dom";
import { useTheme } from "../../providers/ThemeProvider";

export default function CalendarView({ tickets = [], role = "lawyer" }) {
  const { isDark } = useTheme();
  const [currentDate, setCurrentDate] = useState(new Date());
  const [miniDate, setMiniDate] = useState(new Date());
  const [viewType, setViewType] = useState("week"); // "month" or "week"
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [showSidebar, setShowSidebar] = useState(false);
  
  // Real-time state for time marker line
  const [now, setNow] = useState(new Date());

  // Update clock every minute
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 60000);
    return () => clearInterval(timer);
  }, []);

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();

  // Helper: Get start of a week (Sunday)
  const getStartOfWeek = (d) => {
    const date = new Date(d);
    const day = date.getDay();
    const diff = date.getDate() - day; // Adjust to Sunday
    return new Date(date.setDate(diff));
  };

  // Navigations
  const goToday = () => {
    const today = new Date();
    setCurrentDate(today);
    setMiniDate(today);
  };

  const prevRange = () => {
    if (viewType === "month") {
      setCurrentDate(new Date(year, month - 1, 1));
    } else {
      const prevWeek = new Date(currentDate);
      prevWeek.setDate(prevWeek.getDate() - 7);
      setCurrentDate(prevWeek);
    }
  };

  const nextRange = () => {
    if (viewType === "month") {
      setCurrentDate(new Date(year, month + 1, 1));
    } else {
      const nextWeek = new Date(currentDate);
      nextWeek.setDate(nextWeek.getDate() + 7);
      setCurrentDate(nextWeek);
    }
  };

  // Mini-calendar month navigation
  const prevMiniMonth = () => {
    setMiniDate(new Date(miniDate.getFullYear(), miniDate.getMonth() - 1, 1));
  };

  const nextMiniMonth = () => {
    setMiniDate(new Date(miniDate.getFullYear(), miniDate.getMonth() + 1, 1));
  };

  // Fetch days in a month for grids
  const getDaysInMonth = (y, m) => new Date(y, m + 1, 0).getDate();
  const getFirstDayIndex = (y, m) => new Date(y, m, 1).getDay();

  // Group booked & resolved consultations
  const bookedTickets = tickets.filter(
    (t) => (t.status === "booked" || t.status === "resolved") && t.booking_confirmed_at
  );

  const getLocalDateKey = (isoString) => {
    if (!isoString) return "";
    const d = new Date(isoString);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  };

  const bookingsByDate = {};
  bookedTickets.forEach((ticket) => {
    const dateKey = getLocalDateKey(ticket.booking_confirmed_at);
    if (dateKey) {
      if (!bookingsByDate[dateKey]) {
        bookingsByDate[dateKey] = [];
      }
      bookingsByDate[dateKey].push(ticket);
    }
  });

  const monthNames = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
  ];

  const formatEventTime = (isoString) => {
    const date = new Date(isoString);
    return date.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: true,
    });
  };

  const formatFullDate = (isoString) => {
    const date = new Date(isoString);
    return date.toLocaleDateString("en-US", {
      weekday: "long",
      year: "numeric",
      month: "long",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: true,
    });
  };

  // Get date range header text (e.g. "June 2026" or "Jun 14 – 20, 2026")
  const getDateRangeHeader = () => {
    if (viewType === "month") {
      return `${monthNames[month]} ${year}`;
    } else {
      const start = getStartOfWeek(currentDate);
      const end = new Date(start);
      end.setDate(start.getDate() + 6);
      
      const startMonth = start.toLocaleString("en-US", { month: "short" });
      const endMonth = end.toLocaleString("en-US", { month: "short" });
      
      if (start.getFullYear() !== end.getFullYear()) {
        return `${startMonth} ${start.getDate()}, ${start.getFullYear()} – ${endMonth} ${end.getDate()}, ${end.getFullYear()}`;
      }
      if (start.getMonth() !== end.getMonth()) {
        return `${startMonth} ${start.getDate()} – ${endMonth} ${end.getDate()}, ${year}`;
      }
      return `${startMonth} ${start.getDate()} – ${end.getDate()}, ${year}`;
    }
  };

  // Build grid calendar cells for mini-calendar (Sunday-first grid)
  const getMiniCalendarCells = () => {
    const y = miniDate.getFullYear();
    const m = miniDate.getMonth();
    const totalDays = getDaysInMonth(y, m);
    const firstDay = getFirstDayIndex(y, m);
    const cells = [];
    
    // Previous month padding
    const prevM = m === 0 ? 11 : m - 1;
    const prevY = m === 0 ? y - 1 : y;
    const prevTotalDays = getDaysInMonth(prevY, prevM);
    for (let i = firstDay - 1; i >= 0; i--) {
      cells.push({ day: prevTotalDays - i, isPadding: true, dateObj: new Date(prevY, prevM, prevTotalDays - i) });
    }
    
    // Current month
    for (let d = 1; d <= totalDays; d++) {
      cells.push({ day: d, isPadding: false, dateObj: new Date(y, m, d) });
    }
    
    // Next month padding
    const nextM = m === 11 ? 0 : m + 1;
    const nextY = m === 11 ? y + 1 : y;
    const remaining = 42 - cells.length;
    for (let d = 1; d <= remaining; d++) {
      cells.push({ day: d, isPadding: true, dateObj: new Date(nextY, nextM, d) });
    }
    return cells;
  };

  // Check if dates match
  const isSameDay = (d1, d2) => {
    return (
      d1.getDate() === d2.getDate() &&
      d1.getMonth() === d2.getMonth() &&
      d1.getFullYear() === d2.getFullYear()
    );
  };

  // Active week dates list
  const getActiveWeekDates = () => {
    const start = getStartOfWeek(currentDate);
    const dates = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      dates.push(d);
    }
    return dates;
  };

  // Hours layout (8:00 AM - 6:00 PM)
  const hoursList = [];
  for (let h = 8; h <= 18; h++) {
    hoursList.push(h);
  }

  const activeWeek = getActiveWeekDates();

  return (
    <div className={`h-full flex flex-col rounded-3xl border overflow-hidden shadow-2xl transition-colors duration-200 animate-in fade-in duration-300 ${
      isDark 
        ? "bg-[#0b0f19] text-slate-100 border-slate-800/80" 
        : "bg-white text-slate-900 border-slate-200"
    }`}>
      
      {/* ── TOP BAR ── */}
      <header className={`h-16 flex items-center justify-between px-3 sm:px-6 border-b transition-colors duration-200 z-10 ${
        isDark ? "border-slate-800 bg-[#0f172a]/60" : "border-slate-200 bg-slate-50/80"
      }`}>
        <div className="flex items-center gap-2 sm:gap-6 min-w-0">
          <button 
            onClick={() => setShowSidebar(true)}
            className={`lg:hidden p-1.5 hover:text-indigo-500 transition-colors ${isDark ? "text-slate-400" : "text-slate-600"}`}
          >
            <MenuIcon size={20} />
          </button>
          
          <div className="flex items-center gap-2 shrink-0">
            <div className="h-9 w-9 sm:h-10 sm:w-10 rounded-xl bg-indigo-600 flex items-center justify-center text-white shadow-lg shadow-indigo-600/25">
              <CalIcon size={18} />
            </div>
            <span className="font-bold text-base sm:text-lg tracking-tight hidden md:inline">Calendar</span>
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            <button 
              onClick={goToday}
              className={`px-3 py-1.5 border rounded-lg text-[10px] font-black uppercase tracking-wider transition-all hover:bg-indigo-600/10 ${
                isDark 
                  ? "border-slate-700 hover:border-slate-500 text-slate-200" 
                  : "border-slate-200 hover:border-slate-400 text-slate-700"
              }`}
            >
              Today
            </button>
            <div className={`flex items-center gap-0.5 border rounded-lg p-0.5 ${
              isDark ? "bg-slate-900 border-slate-800" : "bg-slate-100 border-slate-200"
            }`}>
              <button 
                onClick={prevRange}
                className={`p-1 rounded-md transition-colors ${
                  isDark ? "hover:bg-slate-800 text-slate-400 hover:text-white" : "hover:bg-slate-200 text-slate-600 hover:text-black"
                }`}
              >
                <ChevronLeft size={13} />
              </button>
              <button 
                onClick={nextRange}
                className={`p-1 rounded-md transition-colors ${
                  isDark ? "hover:bg-slate-800 text-slate-400 hover:text-white" : "hover:bg-slate-200 text-slate-600 hover:text-black"
                }`}
              >
                <ChevronRight size={13} />
              </button>
            </div>
          </div>

          <h2 className={`text-xs sm:text-sm font-bold truncate max-w-[100px] xs:max-w-[160px] sm:max-w-none ${
            isDark ? "text-slate-200" : "text-slate-850"
          }`}>
            {getDateRangeHeader()}
          </h2>
        </div>

        <div className="flex items-center gap-4">
          {/* View switcher dropdown */}
          <div className="relative">
            <div className={`flex border rounded-xl p-1 gap-1 ${
              isDark ? "bg-slate-900 border-slate-800" : "bg-slate-100 border-slate-200"
            }`}>
              <button
                onClick={() => setViewType("week")}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                  viewType === "week" 
                    ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/10" 
                    : isDark ? "text-slate-400 hover:text-white" : "text-slate-600 hover:text-black"
                }`}
              >
                Week
              </button>
              <button
                onClick={() => setViewType("month")}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                  viewType === "month" 
                    ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/10" 
                    : isDark ? "text-slate-400 hover:text-white" : "text-slate-600 hover:text-black"
                }`}
              >
                Month
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* ── MAIN WORKSPACE ── */}
      <div className="flex-1 flex overflow-hidden">
        
        {/* LEFT SIDEBAR (Collapsible drawer overlay on mobile, static sidebar on desktop) */}
        {showSidebar && (
          <div 
            onClick={() => setShowSidebar(false)}
            className="lg:hidden fixed inset-0 bg-black/50 backdrop-blur-sm z-40"
          />
        )}

        <aside className={`w-64 border-r flex flex-col p-6 gap-8 overflow-y-auto select-none transition-all duration-300 z-50 lg:z-0 lg:static ${
          showSidebar 
            ? "flex fixed inset-y-0 left-0" 
            : "hidden lg:flex"
        } ${
          isDark ? "border-slate-800 bg-[#0c1222] lg:bg-[#0c1222]/40 text-slate-100" : "border-slate-200 bg-white lg:bg-slate-50/50 text-slate-900"
        }`}>
          
          <div className="flex items-center justify-between lg:hidden">
            <span className="text-xs font-black uppercase tracking-widest text-slate-450 dark:text-slate-500">Calendar Menu</span>
            <button 
              onClick={() => setShowSidebar(false)} 
              className={`p-1.5 rounded-lg transition-colors ${isDark ? "hover:bg-slate-800 text-slate-400 hover:text-white" : "hover:bg-slate-100 text-slate-500 hover:text-black"}`}
            >
              <X size={16} />
            </button>
          </div>

          {/* Mini Calendar Widget */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className={`text-xs font-bold ${isDark ? "text-slate-200" : "text-slate-800"}`}>
                {monthNames[miniDate.getMonth()]} {miniDate.getFullYear()}
              </span>
              <div className="flex gap-1">
                <button 
                  onClick={prevMiniMonth}
                  className={`p-1 rounded transition-colors ${
                    isDark ? "hover:bg-slate-800 text-slate-400 hover:text-white" : "hover:bg-slate-200 text-slate-600 hover:text-black"
                  }`}
                >
                  <ChevronLeft size={12} />
                </button>
                <button 
                  onClick={nextMiniMonth}
                  className={`p-1 rounded transition-colors ${
                    isDark ? "hover:bg-slate-800 text-slate-400 hover:text-white" : "hover:bg-slate-200 text-slate-600 hover:text-black"
                  }`}
                >
                  <ChevronRight size={12} />
                </button>
              </div>
            </div>

            {/* Mini Grid Header */}
            <div className={`grid grid-cols-7 text-center text-[9px] font-black uppercase tracking-wider ${
              isDark ? "text-slate-500" : "text-slate-400"
            }`}>
              {["S", "M", "T", "W", "T", "F", "S"].map((d, i) => (
                <div key={i}>{d}</div>
              ))}
            </div>

            {/* Mini Grid Days */}
            <div className="grid grid-cols-7 text-center gap-y-1">
              {getMiniCalendarCells().map((cell, idx) => {
                const isSelected = isSameDay(cell.dateObj, currentDate);
                const isCurrentToday = isSameDay(cell.dateObj, new Date());
                
                return (
                  <button
                    key={idx}
                    onClick={() => {
                      setCurrentDate(cell.dateObj);
                      if (cell.isPadding) {
                        setMiniDate(cell.dateObj);
                      }
                      setShowSidebar(false); // Close sidebar on mobile select
                    }}
                    className={`h-7 w-7 text-[10px] font-semibold rounded-full flex items-center justify-center mx-auto transition-all cursor-pointer ${
                      isSelected 
                        ? "bg-indigo-600 text-white font-bold" 
                        : isCurrentToday
                          ? "border border-indigo-600 text-indigo-600 font-bold"
                          : cell.isPadding
                            ? isDark ? "text-slate-600 hover:bg-slate-800/30" : "text-slate-300 hover:bg-slate-100"
                            : isDark ? "text-slate-400 hover:bg-slate-800/60 hover:text-white" : "text-slate-600 hover:bg-slate-200 hover:text-black"
                    }`}
                  >
                    {cell.day}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Calendar checklists */}
          <div className="space-y-4">
            <h3 className={`text-[10px] font-black uppercase tracking-widest ${isDark ? "text-slate-500" : "text-slate-400"}`}>My Calendars</h3>
            <div className="space-y-3">
              <label className={`flex items-center gap-3 cursor-pointer group text-xs font-semibold ${
                isDark ? "text-slate-300 hover:text-white" : "text-slate-700 hover:text-black"
              }`}>
                <input 
                  type="checkbox" 
                  defaultChecked 
                  className={`rounded focus:ring-0 focus:ring-offset-0 h-4.5 w-4.5 cursor-pointer ${
                    isDark ? "border-slate-700 bg-slate-800 text-indigo-600" : "border-slate-300 bg-white text-indigo-600"
                  }`}
                />
                <span>Consultations</span>
                <span className="w-2.5 h-2.5 rounded-full bg-indigo-500 ml-auto shrink-0" />
              </label>
            </div>
          </div>
        </aside>

        {/* MAIN GRID WINDOW */}
        <main className="flex-1 flex flex-col overflow-y-auto overflow-x-auto">
          
          {/* MONTH VIEW */}
          {viewType === "month" && (
            <div className={`flex-1 grid grid-cols-7 gap-px select-none ${
              isDark ? "bg-slate-800/40" : "bg-slate-200/40"
            }`}>
              {/* Days header */}
              <div className={`col-span-7 grid grid-cols-7 border-b text-center text-[10px] font-black uppercase tracking-widest py-3 ${
                isDark ? "border-slate-800 bg-slate-950/40 text-slate-500" : "border-slate-200 bg-slate-50/40 text-slate-400"
              }`}>
                {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map(d => (
                  <div key={d}>{d}</div>
                ))}
              </div>

              {/* Month Days */}
              {(() => {
                const totalDays = getDaysInMonth(year, month);
                const firstDayIdx = getFirstDayIndex(year, month);
                const cells = [];

                // Pad preceding days
                const prevM = month === 0 ? 11 : month - 1;
                const prevY = month === 0 ? year - 1 : year;
                const prevTotalDays = getDaysInMonth(prevY, prevM);
                for (let i = firstDayIdx - 1; i >= 0; i--) {
                  cells.push({ day: prevTotalDays - i, isPadding: true, dateStr: `${prevY}-${String(prevM + 1).padStart(2, "0")}-${String(prevTotalDays - i).padStart(2, "0")}` });
                }

                // Current days
                for (let d = 1; d <= totalDays; d++) {
                  cells.push({ day: d, isPadding: false, dateStr: `${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}` });
                }

                // Pad subsequent days to complete grid rows
                const remaining = cells.length % 7 === 0 ? 0 : 7 - (cells.length % 7);
                const nextM = month === 11 ? 0 : month + 1;
                const nextY = month === 11 ? year + 1 : year;
                for (let d = 1; d <= remaining; d++) {
                  cells.push({ day: d, isPadding: true, dateStr: `${nextY}-${String(nextM + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}` });
                }

                return cells.map((cell, idx) => {
                  const dayBookings = bookingsByDate[cell.dateStr] || [];
                  const isCurrentToday = !cell.isPadding && isSameDay(new Date(year, month, cell.day), new Date());

                  return (
                    <div 
                      key={idx}
                      className={`min-h-[140px] p-2.5 border-b border-r flex flex-col justify-between transition-colors ${
                        isDark ? "border-slate-800/80" : "border-slate-200"
                      } ${
                        cell.isPadding 
                          ? isDark ? "bg-slate-950/10 opacity-30 select-none" : "bg-slate-100/30 opacity-40 select-none" 
                          : isDark ? "bg-[#0c1222]/20 hover:bg-slate-900/30" : "bg-white hover:bg-slate-50"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className={`text-[11px] font-bold ${
                          isCurrentToday 
                            ? "h-6 w-6 rounded-full bg-indigo-600 text-white flex items-center justify-center font-black"
                            : isDark ? "text-slate-400" : "text-slate-600"
                        }`}>
                          {cell.day}
                        </span>
                        {dayBookings.length > 0 && (
                          <span className={`text-[8px] font-black px-1.5 py-0.5 rounded ${
                            isDark ? "text-indigo-400 bg-indigo-500/10 border border-indigo-500/10" : "text-indigo-700 bg-indigo-50 border border-indigo-200"
                          }`}>
                            {dayBookings.length}
                          </span>
                        )}
                      </div>

                      {/* Event pills stack */}
                      <div className="flex-1 mt-2 space-y-1 overflow-y-auto max-h-[85px] sidebar-scrollbar-hidden py-1">
                        {!cell.isPadding && dayBookings.map((ticket, tIdx) => (
                          <button
                            key={tIdx}
                            onClick={() => setSelectedEvent(ticket)}
                            className={`w-full text-left px-2 py-1 rounded text-[9px] font-semibold truncate block cursor-pointer transition-all ${
                              isDark 
                                ? "bg-indigo-600/15 hover:bg-indigo-600/30 border border-indigo-500/15 text-indigo-300" 
                                : "bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 text-indigo-750"
                            }`}
                          >
                            {formatEventTime(ticket.booking_confirmed_at)} {ticket.user_display_name}
                          </button>
                        ))}
                      </div>
                    </div>
                  );
                });
              })()}
            </div>
          )}

          {/* WEEK VIEW (HOURLY GRID) */}
          {viewType === "week" && (
            <div className="flex-1 flex flex-col relative select-none" style={{ minWidth: "700px" }}>
              
              {/* Day header row */}
              <div className={`grid grid-cols-[60px_1fr] border-b sticky top-0 z-20 transition-colors duration-200 ${
                isDark ? "border-slate-800/80 bg-slate-950/20" : "border-slate-200 bg-slate-50/80"
              }`}>
                <div className={`border-r flex items-center justify-center text-[9px] font-bold ${
                  isDark ? "border-slate-800 text-slate-500" : "border-slate-200 text-slate-400"
                }`}>
                  GMT+5.5
                </div>
                
                <div className="grid grid-cols-7">
                  {activeWeek.map((day, idx) => {
                    const isCurrentToday = isSameDay(day, new Date());
                    return (
                      <div 
                        key={idx} 
                        className={`py-3 flex flex-col items-center gap-1 border-r last:border-r-0 ${
                          isDark ? "border-slate-800" : "border-slate-200"
                        } ${
                          isCurrentToday ? "bg-indigo-600/5" : ""
                        }`}
                      >
                        <span className={`text-[10px] font-black uppercase tracking-widest ${
                          isDark ? "text-slate-400" : "text-slate-500"
                        }`}>
                          {day.toLocaleString("en-US", { weekday: "short" })}
                        </span>
                        <span className={`text-base font-black ${
                          isCurrentToday 
                            ? "h-8 w-8 rounded-full bg-indigo-600 text-white flex items-center justify-center shadow-lg shadow-indigo-600/20" 
                            : isDark ? "text-slate-200" : "text-slate-800"
                        }`}>
                          {day.getDate()}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Grid Content with Hour Rows */}
              <div className="flex-1 grid grid-cols-[60px_1fr] relative" style={{ height: "640px" }}>
                
                {/* Time labels column */}
                <div className={`border-r flex flex-col transition-colors duration-200 ${
                  isDark ? "border-slate-800 bg-[#0c111e]/20" : "border-slate-200 bg-slate-50/20"
                }`}>
                  {hoursList.map((hour) => (
                    <div 
                      key={hour} 
                      className={`h-16 border-b pr-2 flex items-start justify-end text-[10px] font-bold pt-1.5 ${
                        isDark ? "border-slate-800/40 text-slate-500" : "border-slate-200/40 text-slate-400"
                      }`}
                    >
                      {hour === 12 ? "12 PM" : hour > 12 ? `${hour - 12} PM` : `${hour} AM`}
                    </div>
                  ))}
                </div>

                {/* Main 7 Columns Canvas */}
                <div className={`grid grid-cols-7 relative transition-colors duration-200 ${
                  isDark ? "bg-[#090d16]/30" : "bg-white"
                }`}>
                  {/* Grid Lines Overlay */}
                  {hoursList.map((hour) => (
                    <div 
                      key={hour} 
                      className={`absolute left-0 right-0 border-b ${
                        isDark ? "border-slate-800/40" : "border-slate-200/40"
                      }`}
                      style={{ top: `${(hour - 8) * 64}px`, height: "64px" }}
                    />
                  ))}

                  {/* Day Columns */}
                  {activeWeek.map((day, dayIdx) => {
                    const dateStr = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;
                    const dayBookings = bookingsByDate[dateStr] || [];
                    const isCurrentToday = isSameDay(day, now);

                    return (
                      <div 
                        key={dayIdx} 
                        className={`relative border-r last:border-r-0 h-[704px] ${
                          isDark ? "border-slate-800" : "border-slate-200"
                        }`}
                      >
                        {/* Red Time Marker Line */}
                        {isCurrentToday && now.getHours() >= 8 && now.getHours() <= 18 && (
                          <div 
                            className="absolute left-0 right-0 flex items-center z-30 pointer-events-none"
                            style={{ 
                              top: `${(now.getHours() - 8) * 64 + (now.getMinutes() / 60) * 64}px` 
                            }}
                          >
                            {/* Circle Pin */}
                            <div className="w-2 h-2 rounded-full bg-red-500 -ml-1 shadow-lg shadow-red-500/50" />
                            {/* Horizontal Line */}
                            <div className="flex-1 h-[2px] bg-red-500" />
                          </div>
                        )}

                        {/* Events absolute container */}
                        {dayBookings.map((ticket, tIdx) => {
                          const eventTime = new Date(ticket.booking_confirmed_at);
                          const startHour = eventTime.getHours();
                          const startMins = eventTime.getMinutes();
                          
                          // Check if event falls in rendering timeline (8 AM - 6 PM)
                          if (startHour >= 8 && startHour <= 18) {
                            const topOffset = (startHour - 8) * 64 + (startMins / 60) * 64;
                            const heightOffset = 32; // Default 30-min booking is 32px high

                            return (
                              <button
                                key={tIdx}
                                onClick={() => setSelectedEvent(ticket)}
                                style={{ 
                                  top: `${topOffset}px`, 
                                  height: `${heightOffset}px` 
                                }}
                                className="absolute left-1.5 right-1.5 rounded-lg bg-indigo-600 border border-indigo-500/50 p-1.5 text-left text-white shadow-lg shadow-indigo-600/10 cursor-pointer overflow-hidden group hover:scale-[1.01] hover:bg-indigo-500 z-10 transition-all"
                              >
                                <div className="text-[9px] font-bold truncate leading-none mb-0.5">
                                  {ticket.user_display_name || "Client Booking"}
                                </div>
                                <div className="text-[7.5px] font-medium text-indigo-200/90 truncate leading-none">
                                  {formatEventTime(ticket.booking_confirmed_at)} - {role === "admin" ? (ticket.lawyer_name || "Admin") : "Claimed"}
                                </div>
                              </button>
                            );
                          }
                          return null;
                        })}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* Booking Details Modal */}
      {selectedEvent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className={`relative w-full max-w-md rounded-2xl border p-5 shadow-2xl animate-in zoom-in-95 duration-200 transition-colors ${
            isDark ? "bg-slate-900 border-slate-800 text-slate-200" : "bg-white border-slate-200 text-slate-800"
          }`}>
            {/* Modal Header */}
            <div className={`flex items-center justify-between mb-4 pb-3 border-b ${isDark ? "border-slate-800" : "border-slate-200"}`}>
              <div className="flex items-center gap-2">
                <Video className="text-indigo-400 h-4.5 w-4.5" />
                <h3 className={`text-base font-bold ${isDark ? "text-white" : "text-slate-900"}`}>Consultation Details</h3>
              </div>
              <button 
                onClick={() => setSelectedEvent(null)}
                className={`p-1 rounded-lg transition-colors cursor-pointer ${
                  isDark ? "text-slate-400 hover:text-white hover:bg-slate-800" : "text-slate-500 hover:text-black hover:bg-slate-100"
                }`}
              >
                <X size={16} />
              </button>
            </div>

            {/* Modal Content */}
            <div className="space-y-4">
              {/* Event Time */}
              <div className={`p-3 rounded-xl border flex items-start gap-3 ${
                isDark ? "border-indigo-500/20 bg-indigo-500/5" : "border-indigo-200 bg-indigo-55/20"
              }`}>
                <Clock className="text-indigo-400 h-4.5 w-4.5 mt-0.5 shrink-0" />
                <div>
                  <h4 className={`text-[10px] font-black uppercase tracking-wider ${isDark ? "text-slate-400" : "text-slate-500"}`}>Scheduled Time</h4>
                  <p className={`text-xs font-bold mt-0.5 ${isDark ? "text-slate-200" : "text-slate-850"}`}>
                    {formatFullDate(selectedEvent.booking_confirmed_at)}
                  </p>
                </div>
              </div>

              {/* Client Info */}
              <div className="space-y-1.5">
                <h4 className={`text-[10px] font-black uppercase tracking-wider flex items-center gap-1.5 ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                  <User size={12} /> Client Details
                </h4>
                <div className={`grid grid-cols-2 gap-3 p-3.5 rounded-xl border ${
                  isDark ? "bg-slate-950/30 border-slate-800/80" : "bg-slate-50 border-slate-200"
                }`}>
                  <div>
                    <span className="text-[9px] text-slate-400 font-bold block">Display Name</span>
                    <span className={`text-xs font-bold ${isDark ? "text-slate-200" : "text-slate-800"}`}>{selectedEvent.user_display_name || "N/A"}</span>
                  </div>
                  <div>
                    <span className="text-[9px] text-slate-400 font-bold block">Email Address</span>
                    <span className={`text-xs font-bold truncate block ${isDark ? "text-slate-200" : "text-slate-800"}`} title={selectedEvent.user_email}>
                      {selectedEvent.user_email || "N/A"}
                    </span>
                  </div>
                </div>
              </div>

              {/* Lawyer Info (Only shown for Admin view) */}
              {role === "admin" && (
                <div className="space-y-1.5">
                  <h4 className={`text-[10px] font-black uppercase tracking-wider flex items-center gap-1.5 ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                    <Shield size={12} /> Assigned Lawyer
                  </h4>
                  <div className={`grid grid-cols-2 gap-3 p-3.5 rounded-xl border ${
                    isDark ? "bg-slate-950/30 border-slate-800/80" : "bg-slate-50 border-slate-200"
                  }`}>
                    <div>
                      <span className="text-[9px] text-slate-400 font-bold block">Lawyer Name</span>
                      <span className={`text-xs font-bold ${isDark ? "text-slate-200" : "text-slate-855"}`}>{selectedEvent.lawyer_name || "N/A"}</span>
                    </div>
                    <div>
                      <span className="text-[9px] text-slate-400 font-bold block">Lawyer Email</span>
                      <span className={`text-xs font-bold truncate block ${isDark ? "text-slate-200" : "text-slate-855"}`} title={selectedEvent.lawyer_email}>
                        {selectedEvent.lawyer_email || "N/A"}
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {/* Status */}
              <div className={`flex items-center justify-between text-xs py-2 px-3.5 rounded-xl border ${
                isDark ? "bg-slate-950/20 border-slate-800/60 text-slate-400" : "bg-slate-50 border-slate-200 text-slate-500"
              }`}>
                <span className="font-semibold text-[10px]">Status:</span>
                <span className={`font-bold capitalize ${selectedEvent.status === 'resolved' ? 'text-emerald-500' : 'text-indigo-500'}`}>
                  {selectedEvent.status}
                </span>
              </div>
            </div>

            {/* Modal Actions */}
            <div className={`mt-8 flex flex-col sm:flex-row gap-3 pt-4 border-t ${isDark ? "border-slate-800" : "border-slate-200"}`}>
              {selectedEvent.status === "resolved" ? (
                <div className={`flex-1 px-4 py-2.5 rounded-xl font-bold text-sm text-center border flex items-center justify-center gap-2 ${
                  isDark ? "bg-slate-800 text-slate-400 border-slate-700/80" : "bg-slate-100 text-slate-400 border-slate-200"
                }`}>
                  <Video size={16} className="opacity-50" />
                  Meeting Finished
                </div>
              ) : selectedEvent.booking_url ? (
                <a
                  href={selectedEvent.booking_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex-1 px-4 py-2.5 rounded-xl bg-indigo-600 text-white font-bold text-sm text-center flex items-center justify-center gap-2 hover:bg-indigo-700 transition-colors shadow-lg shadow-indigo-600/10 cursor-pointer"
                >
                  <Video size={16} />
                  Join Meeting
                  <ExternalLink size={12} />
                </a>
              ) : (
                <div className={`flex-1 px-4 py-2.5 rounded-xl font-semibold text-xs text-center border flex items-center justify-center ${
                  isDark ? "bg-slate-800 text-slate-400 border-slate-700/80" : "bg-slate-100 text-slate-500 border-slate-200"
                }`}>
                  Waiting for Cal.com meeting url...
                </div>
              )}

              <button
                onClick={() => setSelectedEvent(null)}
                className={`px-4 py-2.5 rounded-xl border font-bold text-sm transition-colors cursor-pointer ${
                  isDark 
                    ? "bg-slate-800 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border-slate-800/80" 
                    : "bg-slate-100 hover:bg-slate-200 text-slate-600 hover:text-slate-800 border-slate-200"
                }`}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
