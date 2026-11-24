#if TUBEVAULT_CHECKS
import SwiftUI
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
            try "passed".write(to:documents.appendingPathComponent("checks.txt"),atomically:true,encoding:.utf8)
        } catch {
            try? ("failed: " + String(describing:error)).write(to:documents.appendingPathComponent("checks.txt"),atomically:true,encoding:.utf8)
        }
    }
}
#endif
