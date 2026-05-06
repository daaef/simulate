import { cookies } from "next/headers";
import { redirect } from "next/navigation";

export default function RootEntryPage() {
  const sessionCookie = cookies().get("simulator_session");
  redirect(sessionCookie ? "/overview" : "/auth/login");
}
