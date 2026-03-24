export const initUserCounter = () => {
  if (!localStorage.getItem("userCounter")) {
    localStorage.setItem("userCounter", "1001");
  }
};

export const generateUserId = () => {
  let counter = Number(localStorage.getItem("userCounter")) || 1001;
  const userId = `u_${counter}`;
  localStorage.setItem("userCounter", String(counter + 1));
  return userId;
};
