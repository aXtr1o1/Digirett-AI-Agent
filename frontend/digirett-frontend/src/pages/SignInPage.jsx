import React, { useEffect } from "react";
import SignInForm from "../components/auth/SignInForm";
import { initUserCounter } from "../utils/userId";
const SignInPage = () => {

  useEffect(() => {
    initUserCounter();
  }, []);

  return <SignInForm />;
};

export default SignInPage;
