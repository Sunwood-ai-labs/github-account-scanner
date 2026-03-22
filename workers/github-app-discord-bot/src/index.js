const DEFAULT_WEBHOOK_PATH = "/webhook";
const DEFAULT_USER_AGENT = "github-account-scanner-worker/0.1.0";
const DEFAULT_DEDUPE_TTL_SECONDS = 60 * 60 * 24 * 30;
const DISCORD_API_BASE = "https://discord.com/api/v10";
const DISCORD_CHANNEL_URL_RE =
  /^https:\/\/(?:(?:ptb|canary)\.)?discord\.com\/channels\/\d+\/(\d+)(?:\/\d+)?\/?$/;

function cleanString(value) {
  if (typeof value !== "string") {
    return null;
  }
  const candidate = value.trim();
  return candidate || null;
}

function boolFromEnv(value, fallback = false) {
  const candidate = cleanString(value);
  if (candidate === null) {
    return fallback;
  }
  return ["1", "true", "yes", "on"].includes(candidate.toLowerCase());
}

function jsonResponse(status, payload) {
  return new Response(JSON.stringify(payload, null, 2), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

function normalizePath(value) {
  const candidate = cleanString(value) ?? DEFAULT_WEBHOOK_PATH;
  if (candidate === "/") {
    return "/";
  }
  const normalized = candidate.startsWith("/") ? candidate : `/${candidate}`;
  return normalized.endsWith("/") ? normalized.slice(0, -1) : normalized;
}

function normalizeDiscordChannelId(value) {
  const candidate = cleanString(value);
  if (candidate === null) {
    throw new Error("Discord channel target is empty.");
  }
  if (/^\d+$/.test(candidate)) {
    return candidate;
  }
  const match = candidate.match(DISCORD_CHANNEL_URL_RE);
  if (match) {
    return match[1];
  }
  throw new Error("Discord channel target must be a channel ID or a Discord channel URL.");
}

function escapeMarkdownInline(value) {
  return String(value ?? "unknown").replace(/[`*_~]/g, "\\$&");
}

function truncate(value, maxLength = 2000) {
  const text = String(value ?? "").trim();
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, Math.max(0, maxLength - 1))}…`;
}

function formatJst(isoString) {
  const candidate = cleanString(isoString);
  if (candidate === null) {
    return "unknown";
  }
  const date = new Date(candidate);
  if (Number.isNaN(date.getTime())) {
    return candidate;
  }
  return new Intl.DateTimeFormat("ja-JP", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

async function computeSignature(secret, bodyText) {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const signature = await crypto.subtle.sign("HMAC", key, encoder.encode(bodyText));
  const bytes = new Uint8Array(signature);
  let hex = "";
  for (const value of bytes) {
    hex += value.toString(16).padStart(2, "0");
  }
  return `sha256=${hex}`;
}

function constantTimeEqual(left, right) {
  if (left.length !== right.length) {
    return false;
  }
  let result = 0;
  for (let index = 0; index < left.length; index += 1) {
    result |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return result === 0;
}

async function verifySignature(secret, bodyText, signatureHeader) {
  const signature = cleanString(signatureHeader);
  if (signature === null) {
    return false;
  }
  const expected = await computeSignature(secret, bodyText);
  return constantTimeEqual(expected, signature);
}

function parseJsonObject(bodyText) {
  let parsed;
  try {
    parsed = JSON.parse(bodyText);
  } catch (error) {
    throw new Error(`Invalid webhook JSON payload: ${error}`);
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Webhook JSON payload must be an object.");
  }
  return parsed;
}

function isReleasePublishedEvent(eventName, payload, { includePrereleases = true } = {}) {
  if (eventName !== "release") {
    return false;
  }
  const release = payload.release;
  if (!release || typeof release !== "object") {
    return false;
  }
  const action = cleanString(payload.action);
  // GitHub can emit multiple release activity types around a single publish.
  // We only notify on the canonical published action to avoid double delivery.
  if (action !== "published") {
    return false;
  }
  if (Boolean(release.draft)) {
    return false;
  }
  if (!cleanString(release.published_at)) {
    return false;
  }
  if (!includePrereleases && Boolean(release.prerelease)) {
    return false;
  }
  return true;
}

function buildReleaseKey(payload) {
  const fullName = cleanString(payload?.repository?.full_name) ?? "unknown/unknown";
  const releaseId = payload?.release?.id;
  if (releaseId !== undefined && releaseId !== null) {
    return `${fullName}#${releaseId}`;
  }
  const tagName = cleanString(payload?.release?.tag_name) ?? "unknown-tag";
  const publishedAt =
    cleanString(payload?.release?.published_at) ??
    cleanString(payload?.release?.created_at) ??
    "unknown-time";
  return `${fullName}#${tagName}@${publishedAt}`;
}

function buildReleaseSummary(payload) {
  const repo = payload.repository;
  const release = payload.release;
  const releaseName = cleanString(release.name) ?? cleanString(release.tag_name) ?? "unknown release";
  const publishedAt = cleanString(release.published_at) ?? cleanString(release.created_at) ?? "unknown";
  return {
    repositoryFullName: cleanString(repo.full_name) ?? "unknown/unknown",
    repositoryName: cleanString(repo.name) ?? cleanString(repo.full_name) ?? "unknown-repo",
    repositoryUrl:
      cleanString(repo.html_url) ??
      `https://github.com/${cleanString(repo.full_name) ?? "unknown/unknown"}`,
    releaseName,
    releaseTag: cleanString(release.tag_name) ?? releaseName,
    releaseUrl:
      cleanString(release.html_url) ??
      `${cleanString(repo.html_url) ?? "https://github.com"}/releases`,
    publishedAt,
    publishedAtJst: formatJst(publishedAt),
    body: truncate(cleanString(release.body) ?? "", 700),
    prerelease: Boolean(release.prerelease),
    action: cleanString(payload.action) ?? "published",
  };
}

function buildThreadStarterContent(payload, profile) {
  const summary = buildReleaseSummary(payload);
  const prefix = profile === "test" ? "[test] " : "";
  return [
    `${prefix}${summary.repositoryFullName}: 新しい Release を検知しました`,
    `Release: ${summary.releaseName}`,
    `Tag: ${summary.releaseTag}`,
    "詳細はスレッドに送っています。",
  ].join("\n");
}

function buildThreadName(payload, profile) {
  const summary = buildReleaseSummary(payload);
  const prefix = profile === "test" ? "test " : "";
  return truncate(`${prefix}${summary.repositoryName} ${summary.releaseTag} ${summary.publishedAtJst}`, 100);
}

function buildThreadEmbedPayload(payload, profile) {
  const summary = buildReleaseSummary(payload);
  const descriptionLines = [
    `[${summary.repositoryFullName}](${summary.repositoryUrl}) の release webhook を受信しました。`,
  ];
  if (summary.body) {
    descriptionLines.push("");
    descriptionLines.push(summary.body);
  }
  return {
    embeds: [
      {
        title: `${profile === "test" ? "[test] " : ""}${summary.releaseName}`,
        url: summary.releaseUrl,
        description: descriptionLines.join("\n"),
        color: summary.prerelease ? 0xf1c40f : 0x2ecc71,
        fields: [
          {
            name: "Repository",
            value: `[${summary.repositoryFullName}](${summary.repositoryUrl})`,
            inline: false,
          },
          {
            name: "Tag",
            value: `\`${summary.releaseTag}\``,
            inline: true,
          },
          {
            name: "Action",
            value: `\`${summary.action}\``,
            inline: true,
          },
          {
            name: "Published",
            value: `\`${summary.publishedAt}\``,
            inline: false,
          },
        ],
        footer: {
          text: "github-account-scanner / GitHub App Worker",
        },
        timestamp: cleanString(payload.release.published_at) ?? undefined,
      },
    ],
    allowed_mentions: { parse: [] },
  };
}

function buildMentionPayload(mentionUserId, payload) {
  const summary = buildReleaseSummary(payload);
  return {
    content: `<@${mentionUserId}> ${escapeMarkdownInline(summary.repositoryFullName)} の ${escapeMarkdownInline(summary.releaseTag)} を検知しました。`,
    allowed_mentions: { users: [mentionUserId] },
  };
}

function resolveDiscordConfig(env, profileOverride = null) {
  const profile = cleanString(profileOverride ?? env.DISCORD_DELIVERY_PROFILE ?? "production")?.toLowerCase();
  if (!profile || !["production", "test"].includes(profile)) {
    throw new Error("DISCORD_DELIVERY_PROFILE must be 'production' or 'test'.");
  }

  const explicit = (name) => cleanString(env[name]);
  if (profile === "production") {
    return {
      profile,
      botToken: explicit("DISCORD_PRODUCTION_BOT_TOKEN") ?? explicit("DISCORD_BOT_TOKEN"),
      channelId: normalizeDiscordChannelId(
        explicit("DISCORD_PRODUCTION_CHANNEL_ID") ?? explicit("DISCORD_CHANNEL_ID") ?? ""
      ),
      mentionUserId:
        explicit("DISCORD_PRODUCTION_MENTION_USER_ID") ?? explicit("DISCORD_EXPLAINER_USER_ID"),
    };
  }

  return {
    profile,
    botToken:
      explicit("DISCORD_TEST_BOT_TOKEN") ??
      explicit("DISCORD_PRODUCTION_BOT_TOKEN") ??
      explicit("DISCORD_BOT_TOKEN"),
    channelId: normalizeDiscordChannelId(
      explicit("DISCORD_TEST_CHANNEL_ID") ??
        explicit("DISCORD_PRODUCTION_CHANNEL_ID") ??
        explicit("DISCORD_CHANNEL_ID") ??
        ""
    ),
    mentionUserId: explicit("DISCORD_TEST_MENTION_USER_ID"),
  };
}

async function discordApiRequest(fetchImpl, token, method, path, payload = null) {
  const response = await fetchImpl(`${DISCORD_API_BASE}${path}`, {
    method,
    headers: {
      authorization: `Bot ${token}`,
      "content-type": "application/json",
      accept: "application/json",
      "user-agent": DEFAULT_USER_AGENT,
    },
    body: payload === null ? undefined : JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Discord bot API error ${response.status}: ${body}`);
  }
  if (response.status === 204) {
    return {};
  }
  return response.json();
}

async function sendDiscordNotification(fetchImpl, env, payload, config) {
  if (!config.botToken) {
    throw new Error("Discord bot token is not configured.");
  }

  if (boolFromEnv(env.DRY_RUN_DISCORD, false)) {
    return {
      mode: "dry-run",
      profile: config.profile,
      preview: {
        starter: buildThreadStarterContent(payload, config.profile),
        threadName: buildThreadName(payload, config.profile),
        threadPayload: buildThreadEmbedPayload(payload, config.profile),
        mentionPayload: config.mentionUserId ? buildMentionPayload(config.mentionUserId, payload) : null,
      },
    };
  }

  const starterMessage = await discordApiRequest(
    fetchImpl,
    config.botToken,
    "POST",
    `/channels/${encodeURIComponent(config.channelId)}/messages`,
    {
      content: buildThreadStarterContent(payload, config.profile),
      allowed_mentions: { parse: [] },
    }
  );

  const thread = await discordApiRequest(
    fetchImpl,
    config.botToken,
    "POST",
    `/channels/${encodeURIComponent(config.channelId)}/messages/${encodeURIComponent(starterMessage.id)}/threads`,
    {
      name: buildThreadName(payload, config.profile),
      auto_archive_duration: 1440,
    }
  );

  const detailMessage = await discordApiRequest(
    fetchImpl,
    config.botToken,
    "POST",
    `/channels/${encodeURIComponent(thread.id)}/messages`,
    buildThreadEmbedPayload(payload, config.profile)
  );

  let mentionMessage = null;
  if (config.mentionUserId) {
    mentionMessage = await discordApiRequest(
      fetchImpl,
      config.botToken,
      "POST",
      `/channels/${encodeURIComponent(thread.id)}/messages`,
      buildMentionPayload(config.mentionUserId, payload)
    );
  }

  return {
    mode: "bot",
    profile: config.profile,
    channelId: config.channelId,
    starterMessageId: starterMessage.id,
    threadId: thread.id,
    threadMessageId: detailMessage.id,
    mentionMessageId: mentionMessage?.id ?? null,
  };
}

async function kvGet(kv, key) {
  if (!kv || typeof kv.get !== "function") {
    return null;
  }
  return kv.get(key);
}

async function kvPut(kv, key, value, expirationTtl) {
  if (!kv || typeof kv.put !== "function") {
    return;
  }
  await kv.put(key, value, { expirationTtl });
}

async function markProcessed(env, deliveryId, releaseKey = null) {
  const kv = env.WEBHOOK_STATE;
  if (!kv) {
    return;
  }
  const ttlSeconds = Number.parseInt(cleanString(env.WEBHOOK_STATE_TTL_SECONDS) ?? "", 10);
  const expirationTtl = Number.isFinite(ttlSeconds) ? ttlSeconds : DEFAULT_DEDUPE_TTL_SECONDS;
  const writes = [kvPut(kv, `delivery:${deliveryId}`, new Date().toISOString(), expirationTtl)];
  if (releaseKey) {
    writes.push(kvPut(kv, `release:${releaseKey}`, new Date().toISOString(), expirationTtl));
  }
  await Promise.all(writes);
}

async function detectDuplicate(env, deliveryId, releaseKey = null) {
  const kv = env.WEBHOOK_STATE;
  if (!kv) {
    return { duplicateDelivery: false, duplicateRelease: false, dedupeEnabled: false };
  }
  const [deliverySeen, releaseSeen] = await Promise.all([
    kvGet(kv, `delivery:${deliveryId}`),
    releaseKey ? kvGet(kv, `release:${releaseKey}`) : Promise.resolve(null),
  ]);
  return {
    duplicateDelivery: deliverySeen !== null,
    duplicateRelease: releaseSeen !== null,
    dedupeEnabled: true,
  };
}

async function handleWebhookRequest(request, env) {
  const webhookSecret = cleanString(env.GITHUB_APP_WEBHOOK_SECRET);
  if (webhookSecret === null) {
    return jsonResponse(500, { error: "GITHUB_APP_WEBHOOK_SECRET is not configured." });
  }

  const deliveryId = cleanString(request.headers.get("x-github-delivery"));
  const eventName = cleanString(request.headers.get("x-github-event"))?.toLowerCase() ?? "";
  const signatureHeader = request.headers.get("x-hub-signature-256");
  if (deliveryId === null) {
    return jsonResponse(400, { error: "Missing X-GitHub-Delivery header." });
  }
  if (!eventName) {
    return jsonResponse(400, { error: "Missing X-GitHub-Event header." });
  }

  const bodyText = await request.text();
  const signatureOk = await verifySignature(webhookSecret, bodyText, signatureHeader);
  if (!signatureOk) {
    return jsonResponse(401, { error: "Invalid webhook signature.", deliveryId, eventName });
  }

  const payload = parseJsonObject(bodyText);
  if (eventName === "ping") {
    await markProcessed(env, deliveryId);
    return jsonResponse(200, {
      deliveryId,
      eventName,
      handled: true,
      duplicate: false,
      message: "Ping acknowledged.",
    });
  }

  if (!isReleasePublishedEvent(eventName, payload, { includePrereleases: boolFromEnv(env.INCLUDE_PRERELEASES, true) })) {
    await markProcessed(env, deliveryId);
    return jsonResponse(202, {
      deliveryId,
      eventName,
      action: cleanString(payload.action),
      handled: false,
      duplicate: false,
      message: "Event ignored.",
    });
  }

  const releaseKey = buildReleaseKey(payload);
  const duplicateState = await detectDuplicate(env, deliveryId, releaseKey);
  if (duplicateState.duplicateDelivery || duplicateState.duplicateRelease) {
    await markProcessed(env, deliveryId, releaseKey);
    return jsonResponse(200, {
      deliveryId,
      eventName,
      action: cleanString(payload.action),
      handled: false,
      duplicate: true,
      dedupeEnabled: duplicateState.dedupeEnabled,
      releaseKey,
      message: "Duplicate delivery ignored.",
    });
  }

  let discordResult;
  try {
    const config = resolveDiscordConfig(env);
    discordResult = await sendDiscordNotification(fetch.bind(globalThis), env, payload, config);
  } catch (error) {
    return jsonResponse(500, {
      deliveryId,
      eventName,
      action: cleanString(payload.action),
      handled: false,
      duplicate: false,
      releaseKey,
      error: String(error),
    });
  }

  await markProcessed(env, deliveryId, releaseKey);
  return jsonResponse(200, {
    deliveryId,
    eventName,
    action: cleanString(payload.action),
    handled: true,
    duplicate: false,
    releaseKey,
    discordResult,
  });
}

async function handleRequest(request, env) {
  const url = new URL(request.url);
  const webhookPath = normalizePath(env.GITHUB_APP_WEBHOOK_PATH);

  if (request.method === "GET" && url.pathname === "/") {
    return jsonResponse(200, {
      status: "ok",
      webhookPath,
      deliveryProfile: cleanString(env.DISCORD_DELIVERY_PROFILE) ?? "production",
      dedupeEnabled: Boolean(env.WEBHOOK_STATE),
    });
  }

  if (request.method === "GET" && url.pathname === "/healthz") {
    return jsonResponse(200, { status: "ok" });
  }

  if (request.method === "POST" && url.pathname === webhookPath) {
    return handleWebhookRequest(request, env);
  }

  return jsonResponse(404, { error: "Not found." });
}

export {
  buildReleaseKey,
  buildThreadEmbedPayload,
  buildThreadName,
  buildThreadStarterContent,
  buildMentionPayload,
  computeSignature,
  handleRequest,
  isReleasePublishedEvent,
  normalizeDiscordChannelId,
  normalizePath,
  resolveDiscordConfig,
  verifySignature,
};

export default {
  fetch: handleRequest,
};
