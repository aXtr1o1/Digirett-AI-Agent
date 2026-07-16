import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import adminService from "../../services/adminService";
import { useTheme } from "../../providers/ThemeProvider";

const BackendHealthGuard = ({ children }) => {
  const { isDark } = useTheme();

  const [initialChecking, setInitialChecking] = useState(true);
  const [retrying, setRetrying] = useState(false);

  const [healthStatus, setHealthStatus] = useState({
    ok: false,
    backendReachable: false,
    milvus: null,
    redis: null,
    supabase: null,
    llm: null,
  });

  const intervalRef = useRef(null);

  const checkHealth = useCallback(async ({ manual = false } = {}) => {
    if (manual) {
      setRetrying(true);
    }

    try {
     const data = await adminService.getHealthStatus();
    
      /*
       * These values come directly from the backend health endpoint.
       * Missing values are treated as unhealthy instead of healthy.
       */
      const milvusOk = data?.milvus_connected === true;
      const redisOk = data?.cache_connected === true;
      const supabaseOk = data?.supabase_connected === true;
      const llmOk = data?.llm_connected === true;

      const isDegraded = data?.status === "degraded";

      const overallOk =
        milvusOk &&
        redisOk &&
        supabaseOk &&
        llmOk &&
        !isDegraded;

      const nextHealthStatus = {
        ok: overallOk,
        backendReachable: true,
        milvus: milvusOk,
        redis: redisOk,
        supabase: supabaseOk,
        llm: llmOk,
      };

      setHealthStatus(nextHealthStatus);

      /*
       * Technical information is shown only in the frontend console.
       * The client-facing notification remains generalized.
       */
      if (!overallOk) {
        console.groupCollapsed(
          "%c[DigiRett System Health] Degraded",
          "color: #ef4444; font-weight: bold;"
        );

        console.table({
          "Backend API": true,
          Milvus: milvusOk,
          Redis: redisOk,
          Supabase: supabaseOk,
          LLM: llmOk,
        });

        console.log("Raw backend health response:", data);
        console.groupEnd();
      } else {
        console.info("[DigiRett System Health] All services are healthy.");
      }
    } catch (error) {
      /*
       * The frontend cannot know Milvus/Redis status when the entire
       * backend health endpoint itself is unreachable.
       */
      console.error(
        "[DigiRett System Health] Backend health endpoint unreachable:",
        error
      );

      setHealthStatus({
        ok: false,
        backendReachable: false,
        milvus: null,
        redis: null,
        supabase: null,
        llm: null,
      });
    } finally {
      setInitialChecking(false);
      setRetrying(false);
    }
  }, []);

  /*
   * Run immediately after the authenticated chat route mounts.
   * Continue checking every 20 seconds for automatic recovery.
   */
  useEffect(() => {
    checkHealth();

    intervalRef.current = setInterval(() => {
      checkHealth();
    }, 20000);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [checkHealth]);

  /*
   * Do not show the chat before the first health check completes.
   */
  if (initialChecking) {
    return (
      <div
        className={`min-h-screen flex items-center justify-center p-6 ${
          isDark
            ? "bg-[#09090f] text-white"
            : "bg-slate-50 text-slate-900"
        }`}
      >
        <div className="flex flex-col items-center text-center">
          <RefreshCw className="h-8 w-8 animate-spin text-indigo-500 mb-4" />

          <h2 className="text-lg font-bold mb-2">
            Connecting to DigiRett
          </h2>

          <p
            className={`text-sm ${
              isDark ? "text-gray-400" : "text-gray-500"
            }`}
          >
            Please wait while we verify service availability.
          </p>
        </div>
      </div>
    );
  }

  /*
   * Healthy backend: allow the normal chat application to render.
   */
  if (healthStatus.ok) {
    return children;
  }

  /*
   * Unhealthy backend: show only a generalized client notification.
   */
  return (
    <div
      className={`min-h-screen flex items-center justify-center p-6 ${
        isDark
          ? "bg-[#09090f] text-white"
          : "bg-slate-50 text-slate-900"
      }`}
    >
      <div
        role="alert"
        aria-live="assertive"
        className={`w-full max-w-md rounded-2xl border p-7 text-center shadow-2xl ${
          isDark
            ? "bg-[#12121e] border-amber-500/20"
            : "bg-white border-amber-200"
        }`}
      >
        <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-full bg-amber-500/10">
          <AlertTriangle className="h-7 w-7 text-amber-500" />
        </div>

        <span className="inline-flex rounded-full bg-amber-500/10 px-3 py-1 text-[10px] font-black uppercase tracking-widest text-amber-500 mb-3">
          Temporary Service Issue
        </span>

        <h2 className="text-xl font-bold mb-3">
          DigiRett is temporarily unavailable
        </h2>

        <p
          className={`text-sm leading-6 mb-5 ${
            isDark ? "text-gray-400" : "text-gray-600"
          }`}
        >
          We are currently unable to process requests. Your account,
          conversations, and uploaded documents are safe. Please try again
          shortly.
        </p>

        <div
          className={`rounded-xl border p-4 mb-5 ${
            isDark
              ? "bg-white/[0.03] border-white/10"
              : "bg-slate-50 border-slate-200"
          }`}
        >
          <p
            className={`text-xs leading-5 ${
              isDark ? "text-gray-400" : "text-gray-500"
            }`}
          >
            The connection is being checked automatically. The chat will
            become available as soon as the service is restored.
          </p>
        </div>

        <button
          type="button"
          onClick={() => checkHealth({ manual: true })}
          disabled={retrying}
          className="w-full flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-3 text-sm font-bold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <RefreshCw
            className={`h-4 w-4 ${
              retrying ? "animate-spin" : ""
            }`}
          />

          {retrying ? "Checking Connection..." : "Try Again"}
        </button>
      </div>
    </div>
  );
};

export default BackendHealthGuard;