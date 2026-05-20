import api from "./api";

const notesService = {
  getNotes: async () => {
    const response = await api.get("/notes/");
    return response.data;
  },

  createNote: async (title, content) => {
    const response = await api.post("/notes/", { title, content });
    return response.data;
  },

  updateNote: async (noteId, title, content) => {
    const response = await api.put(`/notes/${noteId}`, { title, content });
    return response.data;
  },

  deleteNote: async (noteId) => {
    const response = await api.delete(`/notes/${noteId}`);
    return response.data;
  }
};

export default notesService;

