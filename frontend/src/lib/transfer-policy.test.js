import {describe, expect, it} from "vitest";
import {TransferPolicy} from "../../../phone/transfer-policy.js";

const MiB = 1024 * 1024;
describe("adaptive phone transfer", () => {
  it("ramps up on sustained quick commits and respects the receiver limit", () => {
    const policy = new TransferPolicy();
    expect(policy.chunkBytes).toBe(MiB);
    policy.completed(MiB, 1000);
    expect(policy.chunkBytes).toBe(MiB);
    policy.completed(MiB, 1000);
    expect(policy.chunkBytes).toBe(2 * MiB);
    for (let i = 0; i < 12; i++) policy.completed(policy.chunkBytes, 1500);
    expect(policy.chunkBytes).toBe(4 * MiB);
  });
  it("backs off slow responses and waits before probing larger pieces again", () => {
    const policy = new TransferPolicy();
    policy.completed(MiB, 9000);
    expect(policy.chunkBytes).toBe(MiB / 2);
    for (let i = 0; i < 4; i++) policy.completed(policy.chunkBytes, 500);
    expect(policy.chunkBytes).toBe(MiB / 2);
    policy.completed(policy.chunkBytes, 500);
    expect(policy.chunkBytes).toBe(MiB);
  });
  it("reduces failed chunks within limits and does not grow from tiny tails", () => {
    const policy = new TransferPolicy();
    for (let i = 0; i < 10; i++) policy.backoff();
    expect(policy.chunkBytes).toBe(MiB / 4);
    for (let i = 0; i < 10; i++) policy.completed(100, 1);
    expect(policy.chunkBytes).toBe(MiB / 4);
  });
  it("adjusts response deadlines to observed speed within safe bounds", () => {
    const policy = new TransferPolicy();
    const initial = policy.timeoutFor(MiB);
    for (let i = 0; i < 5; i++) policy.completed(MiB, 7000);
    expect(policy.timeoutFor(MiB)).toBeGreaterThan(initial);
    expect(policy.timeoutFor(1)).toBe(15000);
    expect(policy.timeoutFor(256 * MiB)).toBe(45000);
  });
});
