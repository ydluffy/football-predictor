import crypto from "crypto";

type EncryptedPayload = {
  v: 1;
  alg: "aes-256-gcm";
  iv: string; // base64
  tag: string; // base64
  data: string; // base64
};

function getKeyBytes(): Buffer {
  const raw = process.env.APP_ENCRYPTION_KEY;
  if (!raw) throw new Error("missing APP_ENCRYPTION_KEY");
  const buf = Buffer.from(raw, "base64");
  if (buf.length !== 32) throw new Error("invalid APP_ENCRYPTION_KEY (must be 32 bytes base64)");
  return buf;
}
export function encryptToJson(plainText: string): string {
  const key = getKeyBytes();
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv("aes-256-gcm", key, iv);
  const enc = Buffer.concat([cipher.update(Buffer.from(plainText, "utf8")), cipher.final()]);
  const tag = cipher.getAuthTag();
  const payload: EncryptedPayload = {
    v: 1,
    alg: "aes-256-gcm",
    iv: iv.toString("base64"),
    tag: tag.toString("base64"),
    data: enc.toString("base64"),
  };
  return JSON.stringify(payload);
}

export function decryptFromJson(payloadJson: string): string {
  const key = getKeyBytes();
  let payload: EncryptedPayload;
  try {
    payload = JSON.parse(payloadJson) as EncryptedPayload;
  } catch {
    throw new Error("invalid encrypted payload (not json)");
  }
  if (!payload || payload.v !== 1 || payload.alg !== "aes-256-gcm") throw new Error("invalid encrypted payload (version/alg)");
  const iv = Buffer.from(payload.iv, "base64");
  const tag = Buffer.from(payload.tag, "base64");
  const data = Buffer.from(payload.data, "base64");
  const decipher = crypto.createDecipheriv("aes-256-gcm", key, iv);
  decipher.setAuthTag(tag);
  const dec = Buffer.concat([decipher.update(data), decipher.final()]);
  return dec.toString("utf8");
}
