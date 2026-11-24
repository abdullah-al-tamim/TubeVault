import SwiftUI
import Photos
import UniformTypeIdentifiers
import Network

@main struct TubeVaultApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var delegate
    @StateObject private var model = Model.shared
    @Environment(\.scenePhase) var phase
    var body: some Scene {
        WindowGroup {
            #if TUBEVAULT_CHECKS
            SimulatorChecks().environmentObject(model)
            #else
            Home().environmentObject(model)
                .task { await model.reconcile(); await model.account() }
                .onChange(of: phase) { if $0 == .active { Task { await model.reconcile() } } }
            #endif
        }
    }
}
struct Home: View {
    @EnvironmentObject var m: Model
    @State private var network = "Checking"
    private let monitor = NWPathMonitor()
    private var dashboard: some View {
            NavigationStack {
                List {
                    Section("YouTube channel") { Text(m.channel?.title ?? "Connect Google in Settings") }
                    Section("Archive") {
                        LabeledContent("Uploaded", value: String(m.jobs.filter { $0.videoID != nil }.count))
                        LabeledContent("Uploaded bytes", value: bytes(m.jobs.filter { $0.videoID != nil }.reduce(0) { $0 + $1.bytes }))
                        LabeledContent("Staged originals", value: bytes(m.jobs.filter { $0.videoID == nil }.reduce(0) { $0 + $1.bytes }))
                        if let space = try? FileManager.default.attributesOfFileSystem(forPath:NSHomeDirectory())[.systemFreeSize] as? NSNumber { LabeledContent("Available storage", value:bytes(space.int64Value)) }
                        LabeledContent("Network",value:network)
                    }
                    Section("Queue activity") {
                        ForEach(Phase.allCases.filter { state in m.jobs.contains { $0.phase == state } },id:\.self) { state in LabeledContent(state.rawValue,value:String(m.jobs.filter { $0.phase == state }.count)) }
                        if m.jobs.isEmpty { Text("Add a video from Photos or Files to get started.") }
                    }
                }.navigationTitle("TubeVault")
            }
    }
    var body: some View {
        TabView {
            dashboard.tabItem { Label("Dashboard",systemImage:"gauge") }
            JobList(archive:false).tabItem { Label("Queue",systemImage:"list.bullet") }
            ImportView().tabItem { Label("Add Videos",systemImage:"plus.circle") }
            JobList(archive:true).tabItem { Label("Archive",systemImage:"archivebox") }
            SettingsView().tabItem { Label("Settings",systemImage:"gear") }
        }
        .onAppear { monitor.pathUpdateHandler = { path in DispatchQueue.main.async { network = path.status != .satisfied ? "Offline" : path.usesInterfaceType(.wifi) ? "Wi-Fi" : path.usesInterfaceType(.cellular) ? "Cellular" : "Connected" } }; monitor.start(queue:DispatchQueue(label:"network")) }
        .alert("TubeVault",isPresented:Binding(get:{ !m.notice.isEmpty }, set:{ if !$0 { m.notice = "" } })) { Button("OK") { m.notice = "" } } message: { Text(m.notice) }
    }
}
func bytes(_ value: Int64) -> String { ByteCountFormatter.string(fromByteCount:value,countStyle:.file) }

struct JobList: View {
    let archive: Bool
    @EnvironmentObject var m: Model
    @State private var search = ""
    @State private var filter = "All"
    @State private var sort = "Newest"
    @State private var playlist = ""
    @State private var selection = Set<UUID>()
    @State private var confirm = false
    var rows: [Job] {
        m.jobs.filter { job in
            (archive ? job.videoID != nil : job.phase != .done) && (filter == "All" || filter == job.phase.rawValue) && (playlist.isEmpty || job.playlistID == playlist) && Rule.matches(search,job.filename)
        }.sorted { a,b in sort == "Size" ? a.bytes > b.bytes : sort == "State" && a.phase != b.phase ? a.phase.rawValue < b.phase.rawValue : a.created > b.created }
    }
    var body: some View {
        NavigationStack {
            List(selection:$selection) {
                if rows.isEmpty { Text(archive ? "No matching archive records." : "No matching queue items.").foregroundStyle(.secondary) }
                ForEach(rows) { job in NavigationLink(value:job.id) {
                    VStack(alignment:.leading, spacing:5) {
                        Text(job.filename).lineLimit(2)
                        Text(job.phase.rawValue + " · " + bytes(job.bytes)).font(.subheadline).foregroundStyle(.secondary)
                        if job.phase == .uploading, let sent = m.sent[job.id] { ProgressView(value:Double(min(job.bytes,job.confirmed + sent)),total:Double(job.bytes)) }
                    }
                }.tag(job.id) }
            }.navigationTitle(archive ? "Archive" : "Queue").searchable(text:$search,prompt:"Search by filename")
            .navigationDestination(for:UUID.self) { JobDetail(id:$0) }
            .toolbar {
                EditButton()
                Menu {
                    Picker("Status",selection:$filter) { Text("All statuses").tag("All"); ForEach(Phase.allCases,id:\.self) { Text($0.rawValue).tag($0.rawValue) } }
                    Picker("Playlist",selection:$playlist) { Text("All playlists").tag(""); ForEach(m.playlists) { Text($0.title).tag($0.id) } }
                    Picker("Sort",selection:$sort) { ForEach(["Newest","Size","State"],id:\.self) { Text($0) } }
                    if !archive { Button("Retry failed items") { Task { for job in m.jobs where job.phase == .failed { await m.run(job.id) } } } }
                } label: { Label("Filter and sort",systemImage:"line.3.horizontal.decrease.circle") }
                if !selection.isEmpty { Button("Remove",role:.destructive) { confirm = true } }
            }.confirmationDialog("Remove selected local records and staged copies?",isPresented:$confirm) {
                Button("Remove eligible records",role:.destructive) { do { for job in m.jobs where selection.contains(job.id) { try m.forget(job) }; selection.removeAll() } catch { m.show(error) } }
            }
        }
    }
}
struct JobDetail: View {
    let id: UUID
    @State private var recoveryID = ""
    @EnvironmentObject var m: Model
    var body: some View {
        List {
            if let job = m.jobs.first(where:{ $0.id == id }) {
                Section(job.filename) {
                    Text(job.phase.rawValue).font(.headline)
                    if !job.detail.isEmpty { Text(job.detail) }
                    LabeledContent("Size",value:bytes(job.bytes))
                    LabeledContent("Confirmed by YouTube",value:bytes(job.confirmed))
                    if let sent = m.sent[id] { LabeledContent("Sent this attempt",value:bytes(sent)) }
                    LabeledContent("Added",value:job.created.formatted())
                    if let date = job.completed { LabeledContent("Accepted",value:date.formatted()) }
                    Text("Source: " + job.source).textSelection(.enabled)
                    Text("Job marker: " + id.uuidString).textSelection(.enabled)
                }
                Section("Destination") {
                    if job.phase == .queued {
                        Picker("Privacy",selection:binding(\.privacy, job)) { Text("Private").tag("private"); Text("Unlisted").tag("unlisted") }
                        Picker("Playlist",selection:binding(\.playlistID, job)) { Text("None").tag(""); ForEach(m.playlists) { Text($0.title).tag($0.id) } }
                    } else { Text(job.privacy.capitalized); Text(m.playlists.first(where:{ $0.id == job.playlistID })?.title ?? (job.playlistID.isEmpty ? "No playlist" : job.playlistID)) }
                }
                if let video = job.videoID, let url = URL(string:"https://www.youtube.com/watch?v=" + video) {
                    Link("Open on YouTube",destination:url)
                    Button("Copy link") { UIPasteboard.general.url = url }
                    Button("Refresh YouTube status") { Task { do {
                        let result = try await m.api.request("videos",["part":"status","id":video])
                        let status = ((result["items"] as? [[String:Any]])?.first?["status"] as? [String:Any])
                        try m.edit(id) { $0.detail = "Remote status: " + (status?["uploadStatus"] as? String ?? "unavailable") + " · " + (status?["privacyStatus"] as? String ?? "unknown visibility") }
                    } catch { m.show(error) } } }
                }
                if job.phase == .uncertain {
                    Section("Recover from YouTube Studio") {
                        TextField("YouTube video ID",text:$recoveryID).textInputAutocapitalization(.never).autocorrectionDisabled()
                        Button("Verify ownership and job marker") { Task { do { try await m.recover(job,video:recoveryID) } catch { m.show(error) } } }
                    }
                }
                if job.phase == .uploading { Button("Pause transfer") { Task { await m.pause(id) } } }
                if [.queued,.paused,.failed,.playlist].contains(job.phase) {
                    Button(job.phase == .playlist ? "Retry playlist association" : job.phase == .queued ? "Start upload" : "Resume or retry") { Task { await m.run(id) } }.disabled(m.busy.contains(id))
                }
            }
        }.navigationTitle("Video details")
    }
    func binding(_ path: WritableKeyPath<Job,String>, _ job: Job) -> Binding<String> {
        Binding(get:{ job[keyPath:path] },set:{ value in do { try m.edit(id) { $0[keyPath:path] = value } } catch { m.show(error) } })
    }
}
struct ImportView: View {
    @EnvironmentObject var m: Model
    @State private var files = false
    @State private var loading = false
    @State private var assets = [PHAsset]()
    @State private var selected = Set<String>()
    @State private var progress = ""
    var body: some View {
        NavigationStack {
            List {
                Button("Choose videos from Files") { files = true }
                Button("Scan permitted Photos videos") { Task {
                    let status = await PHPhotoLibrary.requestAuthorization(for:.readWrite)
                    guard [.authorized,.limited].contains(status) else { m.notice = "Allow Photos access in iPhone Settings."; return }
                    let options = PHFetchOptions()
                    options.sortDescriptors = [NSSortDescriptor(key:"creationDate",ascending:false)]
                    let result = PHAsset.fetchAssets(with:.video,options:options)
                    assets = (0..<result.count).map { result.object(at:$0) }
                } }
                if !assets.isEmpty { Section("Photos") {
                    ForEach(assets,id:\.localIdentifier) { asset in
                        Button { if !selected.insert(asset.localIdentifier).inserted { selected.remove(asset.localIdentifier) } } label: {
                            HStack {
                                VStack(alignment:.leading) { Text(PHAssetResource.assetResources(for:asset).first(where: { $0.type == .video })?.originalFilename ?? "Video"); Text(asset.creationDate?.formatted() ?? "").font(.caption) }
                                Spacer()
                                Image(systemName:selected.contains(asset.localIdentifier) ? "checkmark.circle.fill" : "circle")
                            }
                        }
                    }
                } }
            }.disabled(loading).navigationTitle("Add Videos")
            .safeAreaInset(edge:.bottom) {
                if loading { Text(m.importStatus.isEmpty ? progress : m.importStatus).padding() }
                else if !selected.isEmpty { Button("Queue \(selected.count) selected") { Task {
                    loading = true
                    defer { loading = false }
                    for asset in assets where selected.contains(asset.localIdentifier) {
                        progress = "Staging original"
                        do { try await m.importAsset(asset); selected.remove(asset.localIdentifier) } catch { m.show(error) }
                    }
                } }.buttonStyle(.borderedProminent).padding() }
            }
            .fileImporter(isPresented:$files,allowedContentTypes:[.movie,.video],allowsMultipleSelection:true) { result in
                Task { loading = true; defer { loading = false }
                    do { for file in try result.get() { progress = "Staging " + file.lastPathComponent; do { try await m.importFile(file) } catch { m.show(error) } } } catch { m.show(error) }
                }
            }
        }
    }
}
struct SettingsView: View {
    @EnvironmentObject var m: Model
    @AppStorage("cellular") var cellular = false
    @AppStorage("autoRetry") var autoRetry = false
    @AppStorage("charging") var charging = false
    @AppStorage("concurrency") var concurrency = 1
    @AppStorage("stageGB") var stageGB = 20
    @AppStorage("privacy") var privacy = "private"
    @AppStorage("destination") var destination = ""
    @State private var mapping = ""
    @State private var mappedID = ""
    @State private var title = ""
    @State private var visibility = "private"
    @State private var creating = false
    var body: some View {
        NavigationStack { Form {
            Section("Google and YouTube") {
                if let channel = m.channel { Text(channel.title); Text(channel.id).font(.caption)
                    Button("Disconnect") { do { try m.logout() } catch { m.show(error) } }
                } else { Button("Connect Google account") { Task { await m.account(true) } }.disabled(m.accountBusy) }
            }
            Section("Upload defaults") {
                Toggle("Allow cellular transfers",isOn:$cellular)
                Toggle("Start transfers only on power",isOn:$charging)
                Toggle("Retry temporary server failures",isOn:$autoRetry)
                Stepper("Concurrent uploads: \(concurrency)",value:$concurrency,in:1...4)
                Stepper("Staging limit: \(stageGB) GB",value:$stageGB,in:1...250)
                Picker("Video privacy",selection:$privacy) { Text("Private").tag("private"); Text("Unlisted").tag("unlisted") }
                Picker("Playlist",selection:$destination) { Text("None").tag(""); ForEach(m.playlists) { Text($0.title).tag($0.id) } }
            }
            Section("Album or folder mapping") {
                TextField("Photos album or Files folder name",text:$mapping)
                Picker("Use playlist",selection:$mappedID) { Text("Use default").tag(""); ForEach(m.playlists) { Text($0.title).tag($0.id) } }
                Button("Save mapping") {
                    guard let channel = m.channel else { return }
                    var rules = m.defaults.dictionary(forKey:"mapping." + channel.id) as? [String:String] ?? [:]
                    rules[mapping] = mappedID.isEmpty ? nil : mappedID
                    m.defaults.set(rules,forKey:"mapping." + channel.id)
                    mapping = ""
                }.disabled(mapping.isEmpty || m.channel == nil)
            }
            Section("Create playlist") {
                TextField("Playlist name",text:$title)
                Picker("Playlist visibility",selection:$visibility) { Text("Private").tag("private"); Text("Unlisted").tag("unlisted") }
                Button("Create playlist") { Task {
                    creating = true; defer { creating = false }
                    do { _ = try await m.api.request("playlists",["part":"snippet,status"],body:["snippet":["title":title],"status":["privacyStatus":visibility]])
                        title = ""; m.playlists = try await m.api.list("playlists")
                    } catch { m.show(error) }
                } }.disabled(m.channel == nil || title.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty || creating)
            }
        }.navigationTitle("Settings") }
    }
}
