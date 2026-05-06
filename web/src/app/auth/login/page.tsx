import LoginPageClient from "./LoginPageClient";

export default function LoginPage({
  searchParams,
}: {
  searchParams?: { error?: string };
}) {
  const initialError = searchParams?.error === "invalid_credentials" ? "Invalid username or password" : "";
  return <LoginPageClient initialError={initialError} />;
}
