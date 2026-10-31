import { SignIn } from "@clerk/nextjs";
import { Suspense } from "react";

export default function SignInPage() {
  return (
    <main className="grid min-h-screen place-items-center p-6">
      {/* Clerk reads the URL, which must stream in under Cache Components. */}
      <Suspense>
        <SignIn />
      </Suspense>
    </main>
  );
}
