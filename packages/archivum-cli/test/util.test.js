import test from "node:test";
import assert from "node:assert/strict";

import { parseOptions } from "../src/util.js";

test("parseOptions accepts recovery backup directory as a spaced --dir value", () => {
  const { values, positionals } = parseOptions(["backup", "--dir", "backups/pre-update"]);

  assert.equal(values.get("dir"), "backups/pre-update");
  assert.deepEqual(positionals, ["backup"]);
});
