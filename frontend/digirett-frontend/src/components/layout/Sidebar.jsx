import useConversations from "../../hooks/useConversations";
import { Trash2, MessageSquare } from "lucide-react";

const Sidebar = () => {
  const {
    conversations,
    currentConversationId,
    selectConversation,
    createConversation,
    deleteConversation,
  } = useConversations();

  return (
    <aside className="w-80 bg-[#0f0f0f] border-r border-gray-900 flex flex-col text-white px-4">
      {/* ⭐ APP TITLE (optional like Figma) */}
      <div className="px-4 pt-4 pb-2 text-lg font-semibold">
        DigiRett Legal Assistant
      </div>

      {/* ⭐ New Chat button */}
      <div className="p-3">
        <button
      onClick={createConversation}
      className="w-full flex items-center justify-center gap-2
                bg-white text-black py-4 text-base
                rounded-2xl font-semibold shadow-md
                hover:bg-gray-200 transition"
    >
  <span className="text-xl font-bold">+</span>
  New Chat
</button>
      </div>

      {/* ⭐ Conversation History Heading */}
      <p className="mt-6 mb-3 text-gray-400 text-sm font-semibold tracking-wide">
        Conversation History
      </p>

      {/* ⭐ Conversation list */}
      <div className="flex-1 overflow-y-auto px-2 space-y-1">
        {conversations.length === 0 && (
          <p className="text-gray-500 text-sm px-3 py-2">
            No chats yet
          </p>
        )}

        {conversations.map((c) => (
          <div
            key={c.id}
            onClick={() => selectConversation(c.id)}
            className={`
              flex items-center justify-between gap-2
              px-4 py-3 rounded-lg cursor-pointer transition
              ${
                c.id === currentConversationId
                  ? "bg-[#1f1f1f]"
                  : "hover:bg-[#1a1a1a]"
              }
            `}
          >
            <div className="flex items-center gap-2 truncate">
              <MessageSquare size={14} className="text-gray-500" />
              <span className="truncate text-sm">
                {c.title || "New Conversation"}
              </span>
            </div>

            <Trash2
              size={16}
              onClick={(e) => {
                e.stopPropagation();
                deleteConversation(c.id);
              }}
              className="text-gray-500 hover:text-red-500"
            />
          </div>
        ))}
      </div>
    </aside>
  );
};

export default Sidebar;
