export function localArtifactsEnabled() {
  return process.env.NODE_ENV !== "production" && process.env.ALLOW_LOCAL_ARTIFACTS === "true";
}
