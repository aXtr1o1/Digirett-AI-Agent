import { Trash2, MessageSquare } from "lucide-react";

const Sidebar = ({
  conversations,
  currentConversationId,
  onSelectConversation,
  onNewChat,
  onDeleteConversation,
  theme = "dark",
}) => {
  const isDark = theme === "dark";

  return (
      <aside
        className={`w-96 border-r flex flex-col px-4 transition-colors duration-300 ${
          isDark
          ? "bg-black border-gray-800 text-gray-100"
          : "bg-white border-gray-200 text-gray-900"

        }`}
      >

      {/* ⭐ APP TITLE */}
    <div
      className={`px-4 pt-4 pb-3 text-2xl font-bold ${
        isDark ? "text-white" : "text-gray-900"
      }`}
    >
      DigiRett Legal Assistant
    </div>


      {/* ⭐ New Chat button */}
      <div className="p-3">
        <button
          onClick={onNewChat}
          className={`w-full flex items-center justify-center gap-2
            py-4 text-base rounded-2xl font-semibold shadow-md
            transition ${
              isDark
                ? "bg-white text-black hover:bg-gray-200"
                : "bg-blue-600 text-white hover:bg-blue-700"

            }`}
        >
          <span className="text-xl font-bold">+</span>
          New Chat
        </button>
      </div>

      {/* ⭐ Conversation History Heading */}
      <p
        className={`text-2xl font-bold ${
          isDark ? "text-gray-400" : "text-gray-500"
        }`}
      >
        Conversation History
      </p>


      {/* ⭐ Conversation list */}
      <div className="flex-1 overflow-y-auto px-2 space-y-1">
        {conversations.length === 0 && (
          <p
            className={`text-lg text-gray-400 ${
              isDark ? "text-gray-500" : "text-gray-400"
            }`}
          >
            No chats yet
          </p>
        )}

        {conversations.map((c) => (
          <div
            key={c.conversation_id}
            onClick={() => onSelectConversation(c.conversation_id)}
            className={`
              flex items-center justify-between gap-2
              px-4 py-3 rounded-lg cursor-pointer transition
              ${
                c.conversation_id === currentConversationId
                  ? isDark
                    ? "bg-[#1f1f1f]"
                    : "bg-gray-100"
                  : isDark
                  ? "hover:bg-[#1a1a1a]"
                  : "hover:bg-gray-50"
              }
            `}
          >
            <div className="flex items-center gap-2 truncate">
              <MessageSquare
                size={14}
                className={isDark ? "text-gray-500" : "text-gray-400"}
              />
              <span
                className={`truncate text-lg font-semibold leading-relaxed ${
                  isDark ? "text-gray-100" : "text-gray-900"
                }`}
              >
                {c.title || "New Conversation"}
              </span>
            </div>

            <Trash2
              size={16}
              onClick={(e) => {
                e.stopPropagation();
                onDeleteConversation(c.conversation_id);
              }}
              className={`${
                isDark
                  ? "text-gray-500 hover:text-red-500"
                  : "text-gray-400 hover:text-red-500"
              }`}
            />
          </div>
        ))}
      </div>
    </aside>
  );
};

export default Sidebar;