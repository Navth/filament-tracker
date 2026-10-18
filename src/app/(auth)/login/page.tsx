import { signIn } from "../actions";
import { AuthForm } from "../auth-form";

const ERRORS: Record<string, string> = {
  "not-allowed": "This app is invite-only for now.",
  "confirm-failed": "That confirmation link is invalid or expired. Try signing in, or sign up again.",
};

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const { error } = await searchParams;
  const notice = typeof error === "string" ? ERRORS[error] : undefined;
  return <AuthForm mode="login" action={signIn} notice={notice} />;
}
