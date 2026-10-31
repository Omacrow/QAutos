/**
 * NEXT_PUBLIC_STATIC_PREVIEW=1 builds the marketing site alone as static files
 * (GitHub Pages). There is no backend there, so calls to action point at the
 * scripted live demo and the repository instead of sign-in and the demo workspace.
 */
export const STATIC_PREVIEW = process.env.NEXT_PUBLIC_STATIC_PREVIEW === "1";

export const REPO_URL = "https://github.com/Omacrow/QAutos";
