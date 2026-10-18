import { signUp } from "../actions";
import { AuthForm } from "../auth-form";

export default function SignupPage() {
  return <AuthForm mode="signup" action={signUp} />;
}
