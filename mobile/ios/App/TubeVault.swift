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
                .task { await model.reconcile(); if model.defaults.bool(forKey:"scanOnOpen") { await model.scanPhotos(request:false) }; await model.account() }
                .onChange(of: phase) { if $0 == .active { Task { await model.reconcile() } } }
            #endif
        }
    }
}
struct Home: View {
    @EnvironmentObject var m: Model
    @State private var pickTransfers = false
    @State private var network = "Checking"
    private let monitor = NWPathMonitor()
    private var accepted: [Job] { m.jobs.filter { $0.videoID != nil } }
    private var staged: [Job] { m.jobs.filter { $0.videoID == nil } }
    private var freeBytes: Int64? {
        let attributes = try? FileManager.default.attributesOfFileSystem(forPath:NSHomeDirectory())
        return (attributes?[.systemFreeSize] as? NSNumber)?.int64Value
    }
    private var visiblePhases: [Phase] { Phase.allCases.filter { phase in m.jobs.contains { $0.phase == phase } } }
    private var dashboard: some View {
            NavigationStack {
                List {
                    Section("YouTube channel") { Text(m.channel?.title ?? "Connect Google in Settings") }
                    if !staged.isEmpty {
                        Section("Transfers") {
                            if staged.contains(where:{ $0.phase == .queued }) { Button("Select uploads…") { pickTransfers = true } }
                            ForEach(staged.filter { $0.phase == .uploading } + staged.filter { $0.phase != .uploading }) { job in
                                TransferRow(job:job)
                            }
                        }
                    }
                    Section("Archive") {
                        LabeledContent("Uploaded", value: String(accepted.count))
                        LabeledContent("Uploaded bytes", value: bytes(accepted.reduce(Int64(0)) { $0 + $1.bytes }))
                        LabeledContent("Staged originals", value: bytes(staged.reduce(Int64(0)) { $0 + $1.bytes }))
                        if let freeBytes { LabeledContent("Available storage", value:bytes(freeBytes)) }
                        LabeledContent("Network",value:network)
                    }
                    Section("Queue activity") {
                        ForEach(visiblePhases,id:\.self) { state in LabeledContent(state.rawValue,value:String(m.jobs.filter { $0.phase == state }.count)) }
                        if m.jobs.isEmpty { Text("Add a video from Photos or Files to get started.") }
                    }
                }.navigationTitle("TubeVault")
                .sheet(isPresented:$pickTransfers) { BatchPicker() }
                .navigationDestination(for:UUID.self) { JobDetail(id:$0) }
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
    @State private var cleanup: CleanupSelection?
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
                        Text(job.phase.rawValue + " · " + (job.needsPhotoResource == true ? "In Photos" : bytes(job.bytes))).font(.subheadline).foregroundStyle(.secondary)
                        if job.phase == .uploading { TransferProgress(job:job,meter:m.meter(job.id)) }
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
                if !archive && !selection.isEmpty { Button("Start selected") { m.startSelected(selection); selection.removeAll() }.disabled(m.channel == nil || !rows.contains(where:{ selection.contains($0.id) && $0.phase == .queued })) }
                if !selection.isEmpty { Menu("Actions") {
                    if !archive && rows.contains(where:{ selection.contains($0.id) && $0.phase == .duplicate }) {
                        Button("Upload selected duplicates anyway") {
                            do {
                                let held = rows.filter { selection.contains($0.id) && $0.phase == .duplicate }
                                for job in held { try m.approveDuplicate(job) }
                                m.startSelected(Set(held.map(\.id)))
                                selection.removeAll()
                            } catch { m.show(error) }
                        }.disabled(m.scannedOwner == nil || m.accountBusy)
                        Button("Skip selected duplicates") {
                            do {
                                for job in rows where selection.contains(job.id) && job.phase == .duplicate { try m.forget(job) }
                                selection.removeAll()
                            } catch { m.show(error) }
                        }
                    }
                    if archive { Button("Delete from iPhone…",role:.destructive) {
                        cleanup = CleanupSelection(jobs:rows.filter { selection.contains($0.id) })
                    }.disabled(rows.filter { selection.contains($0.id) }.contains { $0.originalDeleted != nil }) }
                    Button("Remove local records",role:.destructive) { confirm = true } } }
            }.sheet(item:$cleanup) { CleanupReview(records:$0.jobs) }
            .confirmationDialog("Remove selected local records and staged copies?",isPresented:$confirm) {
                Button("Remove eligible records",role:.destructive) { do { for job in m.jobs where selection.contains(job.id) { try m.forget(job) }; selection.removeAll() } catch { m.show(error) } }
            }
        }
    }
}
struct JobDetail: View {
    let id: UUID
    @State private var cleanup: CleanupSelection?
    @State private var recoveryID = ""
    @EnvironmentObject var m: Model
    var body: some View {
        List {
            if let job = m.jobs.first(where:{ $0.id == id }) {
                Section(job.filename) {
                    Text(job.phase.rawValue).font(.headline)
                    if !job.detail.isEmpty { Text(job.detail) }
                    LabeledContent("Size",value:job.needsPhotoResource == true ? "Measured when prepared" : bytes(job.bytes))
                    LabeledContent("Confirmed by YouTube",value:bytes(job.confirmed))
                    if job.phase == .uploading { TransferProgress(job:job,meter:m.meter(id)) }
                    if let duration = job.duration { LabeledContent("Duration",value:String(format:"%.1f s",duration)) }
                    if let path = try? m.storage().media(id).appendingPathExtension("jpg").path,
                       let image = UIImage(contentsOfFile:path) { Image(uiImage:image).resizable().scaledToFit().frame(maxHeight:120).accessibilityLabel("Video thumbnail") }
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
                    if job.originalDeleted != nil { Text("Original deleted from device") }
                    else { Button("Delete from iPhone…",role:.destructive) { cleanup = CleanupSelection(jobs:[job]) } }
                    Link("Open on YouTube",destination:url)
                    Button("Copy link") { UIPasteboard.general.url = url }
                    Button("Refresh YouTube status") { Task { do {
                        let result = try await m.api.request("videos",["part":"status","id":video])
                        let status = ((result["items"] as? [[String:Any]])?.first?["status"] as? [String:Any])
                        try m.edit(id) { $0.detail = "Remote status: " + (status?["uploadStatus"] as? String ?? "unavailable") + " · " + (status?["privacyStatus"] as? String ?? "unknown visibility") }
                    } catch { m.show(error) } } }
                }
                if job.phase == .duplicate {
                    Button("Upload anyway") { do { try m.approveDuplicate(job); m.startSelected([id]) } catch { m.show(error) } }
                    Button("Skip duplicate") { do { try m.forget(job) } catch { m.show(error) } }
                }
                if job.phase == .uncertain {
                    Section("Recover from YouTube Studio") {
                        TextField("YouTube video ID",text:$recoveryID).textInputAutocapitalization(.never).autocorrectionDisabled()
                        Button("Verify ownership and job marker") { Task { do { try await m.recover(job,video:recoveryID) } catch { m.show(error) } } }
                    }
                }
                if job.phase == .waiting { Button("Pause waiting upload") { Task { await m.pause(id) } } }
                if job.phase == .uploading { Button("Pause transfer") { Task { await m.pause(id) } }; Button("Cancel transfer",role:.destructive) { Task { await m.pause(id,cancel:true) } } }
                if [.queued,.paused,.failed,.playlist,.cancelled].contains(job.phase) {
                    Button(job.phase == .playlist ? "Retry playlist association" : job.phase == .queued ? "Start upload" : "Resume or retry") { Task { await m.run(id) } }.disabled(m.busy.contains(id))
                }
            }
        }.navigationTitle("Video details").sheet(item:$cleanup) { CleanupReview(records:$0.jobs) }
    }
    func binding(_ path: WritableKeyPath<Job,String>, _ job: Job) -> Binding<String> {
        Binding(get:{ job[keyPath:path] },set:{ value in do { try m.edit(id) { $0[keyPath:path] = value } } catch { m.show(error) } })
    }
}
struct ImportView: View {
    @EnvironmentObject var m: Model
    @State private var files = false
    @State private var loading = false
    @State private var preview: PreviewAsset?
    private var assets: [PHAsset] { m.photoAssets }
    @State private var selected = Set<String>()
    @State private var progress = ""
    @State private var matches = Set<String>()
    @State private var review = false
    private func enqueue(skip: Bool) {
        let reviewed = matches
        let owner = m.scannedOwner
        loading = true
        Task {
            defer { loading = false }
            for asset in assets where selected.contains(asset.localIdentifier) {
                let id = asset.localIdentifier
                if skip && reviewed.contains(id) { selected.remove(id); continue }
                do {
                    try await m.importAsset(asset,approveFor:reviewed.contains(id) ? owner : nil)
                    selected.remove(id)
                } catch { m.show(error) }
            }
        }
    }
    var body: some View {
        NavigationStack {
            List {
                Section("Duplicate check") {
                    Text(m.accountBusy ? "Checking channel…" : m.scannedOwner != nil ? "Channel titles checked" : "Channel titles unchecked")
                    Button("Refresh channel check") { Task { await m.account() } }.disabled(m.accountBusy)
                }
                Button("Choose videos from Files") { files = true }
                Button("Scan permitted Photos videos") { Task {
                    await m.scanPhotos(request:true)
                } }
                if !assets.isEmpty { Section("Photos") {
                    LazyVGrid(columns:[GridItem(.adaptive(minimum:125), spacing:8)],spacing:8) {
                        ForEach(assets,id:\.localIdentifier) { asset in
                            MovieTile(asset:asset, badge:m.pickerBadge(asset), selected:selected.contains(asset.localIdentifier),
                                      preview:{ preview = PreviewAsset(asset:asset) },
                                      select:{ if !selected.insert(asset.localIdentifier).inserted { selected.remove(asset.localIdentifier) } })
                        }
                    }
                } }
            }.disabled(loading).navigationTitle("Add Videos")
            .safeAreaInset(edge:.bottom) {
                if loading { Text(m.importStatus.isEmpty ? progress : m.importStatus).padding() }
                else if !selected.isEmpty { Button("Queue \(selected.count) selected") {
                    matches = Set(assets.filter { selected.contains($0.localIdentifier) && m.pickerBadge($0) != nil }.map(\.localIdentifier))
                    if matches.isEmpty { enqueue(skip:false) } else { review = true }
                }.buttonStyle(.borderedProminent).padding() }
            }
            .confirmationDialog("\(matches.count) possible duplicates selected",isPresented:$review) {
                Button("Skip matches and queue the rest") { enqueue(skip:true) }
                Button("Queue duplicates anyway") { enqueue(skip:false) }
                Button("Cancel",role:.cancel) {}
            }
            .sheet(item:$preview) { MoviePreview(asset:$0.asset) }
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
    @AppStorage("scanOnOpen") var scanOnOpen = false
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
                Toggle("Scan permitted Photos on launch",isOn:$scanOnOpen)
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
