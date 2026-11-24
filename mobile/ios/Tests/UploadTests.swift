import XCTest
@testable import TubeVaultCore
final class UploadTests: XCTestCase {
    func testAcknowledgedRanges() {
        XCTAssertEqual(Rule.offset(nil, total: 10), 0)
        XCTAssertEqual(Rule.offset("bytes=0-4", total: 10), 5)
        for bad in ["bytes=2-4", "bytes=0-10", "bytes=0--1", "garbage"] { XCTAssertNil(Rule.offset(bad, total: 10)) }
    }
    func testSearchAndIDs() {
        XCTAssertTrue(Rule.matches("Kkt", "Kuakata.mov"))
        XCTAssertFalse(Rule.matches("zz", "Kuakata.mov"))
        XCTAssertFalse(Rule.safeID("../path"))
        XCTAssertTrue(Rule.safeID("a_B-1"))
    }
    func testDurablePlaylistRecovery() throws {
        var job = Job(filename: "ride.mov", source: "Photos", bytes: 10, digest: "sha", privacy: "private", playlistID: "P")
        job.videoID = "abc"
        job.phase = .playlist
        let restored = try JSONDecoder().decode(Job.self, from: JSONEncoder().encode(job))
        XCTAssertEqual(restored.videoID, job.videoID)
        XCTAssertEqual(restored.phase, .playlist)
    }
}
