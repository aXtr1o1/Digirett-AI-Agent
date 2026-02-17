const BASE_URL = "http://localhost:8000/api/v1";
const USER_ID = "2a06144d-4675-4c38-b7f8-13c02da91af5";

export async function runSystemTest() {
  console.log("🚀 Starting Frontend System Test");

  // 1️⃣ Health Check
  const health = await fetch(`${BASE_URL}/health`);
  console.log("Health:", await health.json());

  // 2️⃣ Create Conversation
  const convRes = await fetch(`${BASE_URL}/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: USER_ID,
      title: "Frontend System Test",
    }),
  });

  const convData = await convRes.json();
  const conversationId = convData.conversation_id;
  console.log("Conversation Created:", conversationId);

  // 3️⃣ Streaming Test
  const response = await fetch(`${BASE_URL}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: USER_ID,
      conversation_id: conversationId,
      query: "Explain Norwegian company law briefly.",
      top_k: 3,
    }),
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");

  let fullText = "";
  let sources = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value);
    const lines = chunk.split("\n");

    lines.forEach((line) => {
      if (line.startsWith("data: ")) {
        const data = JSON.parse(line.replace("data: ", ""));
        if (data.type === "token") {
          fullText += data.data;
        }
        if (data.type === "complete") {
          sources = data.metadata.sources;
        }
      }
    });
  }

  console.log("Streamed Answer:", fullText.substring(0, 200));
  console.log("Streamed Sources:", sources);

  // 4️⃣ Fetch Messages
  const messagesRes = await fetch(
    `${BASE_URL}/messages/${conversationId}`
  );
  const messages = await messagesRes.json();

  const assistantMsg = messages.find((m) => m.role === "assistant");

  console.log("Saved Assistant Sources:", assistantMsg?.sources);

  if (!assistantMsg?.sources?.length) {
    console.error("❌ Sources missing after refresh!");
  } else {
    console.log("✅ Sources persisted correctly!");
  }

  console.log("🎉 Frontend Test Completed");
}
