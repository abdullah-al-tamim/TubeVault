#if TUBEVAULT_CHECKS
import SwiftUI
final class MockGoogle: URLProtocol {
    static var revoked = false
    static var inserted = false
    static var processed = false
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func stopLoading() {}
    override func startLoading() {
        var status = 200
        var result: [String:Any] = [:]
        switch (request.url!.path,request.httpMethod) {
        case ("/token",_):
            if Self.revoked { status = 400 } else { result = ["access_token":"test-only","expires_in":3600] }
        case ("/youtube/v3/channels",_), ("/youtube/v3/playlists",_):
            result = ["items":[["id":"test","snippet":["title":"Fixture"]]]]
        case ("/youtube/v3/videos","GET"):
            result = ["items":[["id":"mockvideo01","snippet":["channelId":"test"],"status":["uploadStatus":Self.processed ? "processed" : "uploaded"]]]]
        case ("/youtube/v3/playlistItems","GET"):
            result = ["items":Self.inserted ? [["id":"membership"]] : []]
        case ("/youtube/v3/playlistItems","POST"):
            Self.inserted = true
            result = ["id":"membership"]
        default: status = 404
        }
        client?.urlProtocol(self,didReceive:HTTPURLResponse(url:request.url!,statusCode:status,httpVersion:nil,headerFields:nil)!,cacheStoragePolicy:.notAllowed)
        client?.urlProtocol(self,didLoad:try! JSONSerialization.data(withJSONObject:result))
        client?.urlProtocolDidFinishLoading(self)
    }
}
struct SimulatorChecks: View {
    @EnvironmentObject var m: Model
    var body: some View { Text("TubeVault simulator checks").task { await check() } }
    @MainActor func check() async {
        let documents = FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0]
        func require(_ condition: Bool, _ reason: String) throws { if !condition { throw Problem(reason) } }
        do {
            let source = documents.appendingPathComponent("sample.mov")
            let fixture = Data(repeating:42,count:2_000_000)
            try fixture.write(to:source)
            try await m.importFile(source)
            guard let job = m.jobs.first else { throw Problem("Queue import failed") }
            try require(job.bytes == 2_000_000 && job.privacy == "private" && job.phase == .queued,"Import metadata")
            do { try await m.importFile(source); throw Problem("Duplicate accepted") }
            catch let problem as Problem where problem.message.contains("already has") {}
            let restored = try Storage().load()
            try require(restored.first?.id == job.id && restored.count == 1,"Persistent deduplication")
            try m.edit(job.id) { $0.phase = .creating; $0.channel = "test" }
            await m.reconcile()
            try require(m.jobs.first?.phase == .uncertain,"Ambiguous creation recovery")
            let url = URL(string:"https://www.googleapis.com/upload/mock")!
            try Vault.put(job.id.uuidString, Data(url.absoluteString.utf8))
            try m.edit(job.id) { $0.phase = .uploading }
            await m.reconcile()
            try require(m.jobs.first?.phase == .paused,"Known session recovery")
            m.received(job.id,response:HTTPURLResponse(url:url,statusCode:308,httpVersion:nil,headerFields:["Range":"bytes=0-999"]),data:Data(),interrupted:false)
            try require(m.jobs.first?.confirmed == 1000,"Partial receipt")
            try m.edit(job.id) { $0.playlistID = "mock" }
            let receipt = try JSONSerialization.data(withJSONObject:["id":"mockvideo01"])
            m.received(job.id,response:HTTPURLResponse(url:url,statusCode:200,httpVersion:nil,headerFields:nil),data:receipt,interrupted:false)
            let persisted = try Storage().load().first
            try require(persisted?.phase == .playlist && persisted?.videoID == "mockvideo01","Separate playlist intent")
            try require(try Data(contentsOf:source) == fixture,"Source preservation")
            try require(!FileManager.default.fileExists(atPath:try m.storage().media(job.id).path),"Staging cleanup")
            let config = URLSessionConfiguration.ephemeral
            config.protocolClasses = [MockGoogle.self]
            let google = Google(transport:URLSession(configuration:config),client:"simulator")
            let expired = try JSONEncoder().encode(Credentials(access:"expired",refresh:"simulated",expires:.distantPast))
            try Vault.put("google",expired)
            try require(try await google.token() == "test-only","Token refresh")
            let connected = Model(auth:google)
            await connected.account()
            try require(connected.channel?.id == "test","Authenticated channel")
            await connected.run(job.id)
            try require(MockGoogle.inserted && connected.jobs.first?.phase == .done,"Playlist recovery without second upload")
            let archived = connected.jobs[0]
            var blocked = false
            do { try await connected.verifyBackups([archived]) } catch { blocked = true }
            try require(blocked,"Block cleanup while processing")
            MockGoogle.processed = true
            try await connected.verifyBackups([archived])
            var missing = archived
            missing.videoID = "missing"
            blocked = false
            do { try await connected.verifyBackups([missing]) } catch { blocked = true }
            try require(blocked,"Block cleanup for unavailable video")
            let selected = Job(filename:"batch.mov",source:"fixture",bytes:10,digest:"batch",privacy:"private",playlistID:"")
            let untouched = Job(filename:"other.mov",source:"fixture",bytes:11,digest:"other",privacy:"private",playlistID:"")
            try connected.persist(connected.jobs + [selected,untouched])
            connected.startSelected([selected.id])
            let waiting = try Storage().load()
            try require(waiting.first(where:{ $0.id == selected.id })?.batchOwner == "test","Durable batch owner")
            try require(waiting.first(where:{ $0.id == untouched.id })?.phase == .queued,"Unselected upload stays queued")
            try connected.forget(untouched)
            try require(try Storage().load().allSatisfy { $0.id != untouched.id },"Per-row removal")
            try Vault.put("google",expired)
            MockGoogle.revoked = true
            var refused = false
            do { _ = try await google.token() } catch { refused = true }
            try require(refused,"Revoked credentials")
            try Vault.remove("google")
            try "passed".write(to:documents.appendingPathComponent("checks.txt"),atomically:true,encoding:.utf8)
        } catch {
            try? ("failed: " + String(describing:error)).write(to:documents.appendingPathComponent("checks.txt"),atomically:true,encoding:.utf8)
        }
    }
}
#endif
