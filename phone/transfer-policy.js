// Adapt only from completed, durably acknowledged chunks. One upload at a time.
export class TransferPolicy {
  constructor() {
    this.minimum = 256 * 1024;
    this.maximum = 4 * 1024 * 1024;
    this.chunkBytes = 1024 * 1024;
    this.bytesPerSecond = 512 * 1024;
    this.quickChunks = 0;
    this.cooldown = 0;
  }

  timeoutFor(bytes) {
    return Math.round(Math.min(45000, Math.max(15000,
      8000 + bytes / this.bytesPerSecond * 4000)));
  }

  completed(bytes, milliseconds) {
    const seconds = Math.max(.05, milliseconds / 1000);
    this.bytesPerSecond = .7 * this.bytesPerSecond + .3 * bytes / seconds;
    // A short final piece must not convince us that a full-size piece is fast.
    if (bytes < this.chunkBytes * .75) return;
    if (seconds > 8) {
      this.backoff();
      return;
    }
    if (this.cooldown > 0) {
      this.cooldown--; this.quickChunks = 0;
      return;
    }
    this.quickChunks = seconds <= 3 ? this.quickChunks + 1 : 0;
    if (this.quickChunks >= 2) {
      this.chunkBytes = Math.min(this.maximum, this.chunkBytes * 2);
      this.quickChunks = 0;
    }
  }

  backoff() {
    this.chunkBytes = Math.max(this.minimum, Math.floor(this.chunkBytes / 2));
    this.quickChunks = 0;
    this.cooldown = 3;
    // Give slower connections more time, within a bounded timeout.
    this.bytesPerSecond = Math.max(32 * 1024, this.bytesPerSecond * .75);
  }
}
