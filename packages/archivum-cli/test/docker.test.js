import test from "node:test";
import assert from "node:assert/strict";

import { composeCommand } from "../src/docker.js";

test("composeCommand includes images override when using published images", () => {
  assert.deepEqual(composeCommand(["docker", "compose"], { useImages: true }), [
    "docker",
    "compose",
    "-f",
    "docker-compose.yml",
    "-f",
    "docker-compose.images.yml",
  ]);
});

test("composeCommand uses base compose command for local builds", () => {
  assert.deepEqual(composeCommand(["docker", "compose"], { useImages: false }), [
    "docker",
    "compose",
  ]);
});
