import test from "node:test";
import assert from "node:assert/strict";
import { generateKeyPairSync } from "node:crypto";

import {
  buildReleaseKey,
  computeSignature,
  createGitHubAppJwt,
  handleRequest,
  isReleasePublishedEvent,
  logEvent,
  normalizeDiscordChannelId,
  normalizePath,
  resolveDiscordConfig,
  stampReleaseReaction,
  verifySignature,
} from "../src/index.js";

const { privateKey: githubAppPrivateKeyPem } = generateKeyPairSync("rsa", {
  modulusLength: 2048,
  privateKeyEncoding: {
    type: "pkcs1",
    format: "pem",
  },
  publicKeyEncoding: {
    type: "spki",
    format: "pem",
  },
});

function sampleReleasePayload({
  action = "published",
  draft = false,
  prerelease = false,
  publishedAt = "2026-03-22T11:35:26Z",
} = {}) {
  return {
    action,
    installation: { id: 123456 },
    repository: {
      id: 1,
      name: "github-account-scanner-detection-sample-20260321-195933",
      full_name: "Sunwood-ai-labs/github-account-scanner-detection-sample-20260321-195933",
      html_url: "https://github.com/Sunwood-ai-labs/github-account-scanner-detection-sample-20260321-195933",
    },
    release: {
      id: 299888743,
      tag_name: "v0.1.5",
      name: "v0.1.5",
      html_url:
        "https://github.com/Sunwood-ai-labs/github-account-scanner-detection-sample-20260321-195933/releases/tag/v0.1.5",
      body: "Real release smoke test body",
      draft,
      prerelease,
      created_at: "2026-03-22T11:35:20Z",
      published_at: publishedAt,
    },
  };
}

function buildRequest(secret, payload, headers = {}) {
  return computeSignature(secret, JSON.stringify(payload)).then((signature) =>
    new Request("https://example.com/webhook", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-github-delivery": "delivery-1",
        "x-github-event": "release",
        "x-hub-signature-256": signature,
        ...headers,
      },
      body: JSON.stringify(payload),
    })
  );
}

function createDiscordFetchMock() {
  const calls = [];
  const fetchMock = async (url, init = {}) => {
    calls.push({
      url,
      method: init.method ?? "GET",
      body: init.body ? JSON.parse(init.body) : null,
    });
    if (url.includes("/threads")) {
      return Response.json({ id: "thread-1", name: "thread-name" });
    }
    if (url.endsWith("/messages")) {
      return Response.json({ id: `message-${calls.length}` });
    }
    throw new Error(`Unexpected Discord API mock URL: ${url}`);
  };
  return { calls, fetchMock };
}

function createCombinedFetchMock() {
  const calls = [];
  const fetchMock = async (url, init = {}) => {
    calls.push({
      url,
      method: init.method ?? "GET",
      body: init.body ? JSON.parse(init.body) : null,
    });
    if (String(url).startsWith("https://discord.com/api/v10")) {
      if (url.includes("/threads")) {
        return Response.json({ id: "thread-1", name: "thread-name" });
      }
      if (url.endsWith("/messages")) {
        return Response.json({ id: `message-${calls.length}` });
      }
    }
    if (String(url) === "https://api.github.com/app/installations/123456/access_tokens") {
      return Response.json({ token: "ghs_installation_token" });
    }
    if (
      String(url) ===
      "https://api.github.com/repos/Sunwood-ai-labs/github-account-scanner-detection-sample-20260321-195933/releases/299888743/reactions"
    ) {
      return Response.json({ id: 777, content: "eyes" }, { status: 201 });
    }
    throw new Error(`Unexpected API mock URL: ${url}`);
  };
  return { calls, fetchMock };
}

function createExecutionContextMock() {
  const promises = [];
  return {
    promises,
    waitUntil(promise) {
      promises.push(Promise.resolve(promise));
    },
  };
}

test("normalizePath normalizes slashes", () => {
  assert.equal(normalizePath("/webhook/"), "/webhook");
  assert.equal(normalizePath("github/webhook"), "/github/webhook");
});

test("normalizeDiscordChannelId accepts channel URLs", () => {
  assert.equal(
    normalizeDiscordChannelId("https://discord.com/channels/1188045372526964796/1476217154004058143"),
    "1476217154004058143"
  );
});

test("verifySignature validates signed payloads", async () => {
  const secret = "super-secret";
  const body = JSON.stringify(sampleReleasePayload());
  const signature = await computeSignature(secret, body);

  assert.equal(await verifySignature(secret, body, signature), true);
  assert.equal(await verifySignature(secret, body, "sha256=deadbeef"), false);
});

test("isReleasePublishedEvent only accepts published non-draft releases", () => {
  assert.equal(isReleasePublishedEvent("release", sampleReleasePayload()), true);
  assert.equal(isReleasePublishedEvent("release", sampleReleasePayload({ action: "created" })), false);
  assert.equal(isReleasePublishedEvent("release", sampleReleasePayload({ action: "released" })), false);
  assert.equal(isReleasePublishedEvent("release", sampleReleasePayload({ draft: true })), false);
  assert.equal(isReleasePublishedEvent("release", sampleReleasePayload({ action: "edited" })), false);
});

test("buildReleaseKey uses repository full name and release id", () => {
  assert.equal(
    buildReleaseKey(sampleReleasePayload()),
    "Sunwood-ai-labs/github-account-scanner-detection-sample-20260321-195933#299888743"
  );
});

test("resolveDiscordConfig test profile does not inherit production mentions", () => {
  const config = resolveDiscordConfig({
    DISCORD_DELIVERY_PROFILE: "test",
    DISCORD_BOT_TOKEN: "token",
    DISCORD_CHANNEL_ID: "1476217154004058143",
    DISCORD_PRODUCTION_MENTION_USER_ID: "999999999999999999",
  });

  assert.equal(config.profile, "test");
  assert.equal(config.mentionUserId, null);
});

test("logEvent emits structured logs when the level matches", () => {
  const messages = [];
  const originalConsoleLog = console.log;
  console.log = (value) => {
    messages.push(value);
  };
  try {
    logEvent({ WORKER_LOG_LEVEL: "info" }, "debug", "hidden");
    logEvent({ WORKER_LOG_LEVEL: "info" }, "info", "shown", { deliveryId: "delivery-1" });
  } finally {
    console.log = originalConsoleLog;
  }

  assert.equal(messages.length, 1);
  assert.match(messages[0], /"message":"shown"/);
  assert.match(messages[0], /"deliveryId":"delivery-1"/);
});

test("handleRequest acknowledges ping", async () => {
  const secret = "super-secret";
  const body = JSON.stringify({ zen: "Keep it logically awesome." });
  const signature = await computeSignature(secret, body);
  const response = await handleRequest(
    new Request("https://example.com/webhook", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-github-delivery": "delivery-ping",
        "x-github-event": "ping",
        "x-hub-signature-256": signature,
      },
      body,
    }),
    {
      GITHUB_APP_WEBHOOK_SECRET: secret,
      DISCORD_BOT_TOKEN: "token",
      DISCORD_CHANNEL_ID: "1476217154004058143",
    }
  );
  const payload = await response.json();

  assert.equal(response.status, 200);
  assert.equal(payload.handled, true);
  assert.equal(payload.message, "Ping acknowledged.");
});

test("handleRequest dry-runs release notifications in test profile", async () => {
  const secret = "super-secret";
  const payload = sampleReleasePayload();
  const request = await buildRequest(secret, payload);
  const response = await handleRequest(request, {
    GITHUB_APP_WEBHOOK_SECRET: secret,
    DISCORD_DELIVERY_PROFILE: "test",
    DISCORD_BOT_TOKEN: "token",
    DISCORD_CHANNEL_ID: "1476217154004058143",
    DRY_RUN_DISCORD: "true",
  });
  const body = await response.json();

  assert.equal(response.status, 200);
  assert.equal(body.handled, true);
  assert.equal(body.discordResult.mode, "dry-run");
  assert.equal(body.discordResult.profile, "test");
  assert.match(body.discordResult.preview.starter, /v0\.1\.5/);
});

test("handleRequest posts release notifications to Discord Bot API", async (context) => {
  const secret = "super-secret";
  const payload = sampleReleasePayload();
  const request = await buildRequest(secret, payload, {
    "x-github-delivery": "delivery-discord",
  });
  const { calls, fetchMock } = createDiscordFetchMock();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = fetchMock;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });

  const response = await handleRequest(request, {
    GITHUB_APP_WEBHOOK_SECRET: secret,
    DISCORD_DELIVERY_PROFILE: "test",
    DISCORD_BOT_TOKEN: "token",
    DISCORD_CHANNEL_ID: "1476217154004058143",
  });
  const body = await response.json();

  assert.equal(response.status, 200);
  assert.equal(body.handled, true);
  assert.equal(body.discordResult.mode, "bot");
  assert.equal(body.discordResult.mentionMessageId, null);
  assert.equal(calls.length, 3);
  assert.match(calls[0].body.content, /\[test\]/);
});

test("stampReleaseReaction uses the GitHub App installation token and release reactions API", async (context) => {
  const { calls, fetchMock } = createCombinedFetchMock();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = fetchMock;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });

  const result = await stampReleaseReaction(
    fetchMock,
    {
      GITHUB_APP_ID: "3157685",
      GITHUB_APP_PRIVATE_KEY: githubAppPrivateKeyPem,
      GITHUB_RELEASE_REACTION: "eyes",
    },
    sampleReleasePayload()
  );

  assert.equal(result.mode, "github-app");
  assert.equal(result.content, "eyes");
  assert.equal(result.created, true);
  assert.equal(result.reactionId, 777);
  assert.equal(calls.length, 2);
  assert.equal(calls[0].url, "https://api.github.com/app/installations/123456/access_tokens");
  assert.match(calls[1].url, /\/releases\/299888743\/reactions$/);
});

test("createGitHubAppJwt accepts escaped newline PEM values", async () => {
  const escapedPem = githubAppPrivateKeyPem.replace(/\n/g, "\\n");
  const jwt = await createGitHubAppJwt("3157685", escapedPem);

  assert.match(jwt, /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/);
});

test("handleRequest defers release stamping after the Discord notification", async (context) => {
  const secret = "super-secret";
  const payload = sampleReleasePayload();
  const request = await buildRequest(secret, payload, {
    "x-github-delivery": "delivery-with-reaction",
  });
  const { calls, fetchMock } = createCombinedFetchMock();
  const executionContext = createExecutionContextMock();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = fetchMock;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });

  const response = await handleRequest(request, {
    GITHUB_APP_WEBHOOK_SECRET: secret,
    DISCORD_DELIVERY_PROFILE: "test",
    DISCORD_BOT_TOKEN: "token",
    DISCORD_CHANNEL_ID: "1476217154004058143",
    GITHUB_APP_ID: "3157685",
    GITHUB_APP_PRIVATE_KEY: githubAppPrivateKeyPem,
    GITHUB_RELEASE_REACTION: "eyes",
  }, executionContext);
  const body = await response.json();

  assert.equal(response.status, 200);
  assert.equal(body.handled, true);
  assert.equal(body.discordResult.mode, "bot");
  assert.equal(body.releaseReactionResult.mode, "deferred");
  assert.equal(executionContext.promises.length, 1);
  await Promise.all(executionContext.promises);
  assert.equal(calls.length, 5);
});

test("handleRequest dedupes release replays when KV is bound", async (context) => {
  const secret = "super-secret";
  const payload = sampleReleasePayload();
  const request1 = await buildRequest(secret, payload, {
    "x-github-delivery": "delivery-a",
  });
  const request2 = await buildRequest(secret, payload, {
    "x-github-delivery": "delivery-b",
  });
  const store = new Map();
  const kv = {
    get(key) {
      return Promise.resolve(store.has(key) ? store.get(key) : null);
    },
    put(key, value) {
      store.set(key, value);
      return Promise.resolve();
    },
  };
  const { calls, fetchMock } = createDiscordFetchMock();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = fetchMock;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });

  const env = {
    GITHUB_APP_WEBHOOK_SECRET: secret,
    DISCORD_DELIVERY_PROFILE: "test",
    DISCORD_BOT_TOKEN: "token",
    DISCORD_CHANNEL_ID: "1476217154004058143",
    WEBHOOK_STATE: kv,
  };

  const first = await handleRequest(request1, env);
  const second = await handleRequest(request2, env);
  const firstBody = await first.json();
  const secondBody = await second.json();

  assert.equal(firstBody.handled, true);
  assert.equal(secondBody.duplicate, true);
  assert.equal(calls.length, 3);
});
