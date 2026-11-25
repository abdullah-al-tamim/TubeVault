import SwiftUI
import Photos
import AVKit

struct PreviewAsset: Identifiable {
    let asset: PHAsset
    var id: String { asset.localIdentifier }
}

struct MovieTile: View {
    let asset: PHAsset
    let selected: Bool
    let preview: () -> Void
    let select: () -> Void
    @State private var image: UIImage?
    @State private var request: PHImageRequestID?
    @State private var generation = UUID()

    var body: some View {
        let seconds = Int(asset.duration)
        ZStack(alignment:.topTrailing) {
            Button(action:preview) {
                ZStack(alignment:.bottomLeading) {
                    Color.secondary.opacity(0.18)
                    if let image {
                        GeometryReader { box in
                            Image(uiImage:image).resizable().scaledToFill()
                                .frame(width:box.size.width,height:box.size.height).clipped()
                        }
                    }
                    Label(String(format:"%d:%02d", seconds / 60, seconds % 60),systemImage:"play.fill")
                        .font(.caption.bold()).foregroundStyle(.white).padding(5)
                        .background(.black.opacity(0.65),in:Capsule()).padding(5)
                }.aspectRatio(4/3,contentMode:.fit).clipShape(RoundedRectangle(cornerRadius:10))
            }.buttonStyle(.plain)
            .accessibilityLabel("Preview video, " + (asset.creationDate?.formatted() ?? "") + ", \(seconds) seconds")
            Button(action:select) {
                Image(systemName:selected ? "checkmark.circle.fill" : "circle")
                    .font(.title2).foregroundStyle(.white).background(selected ? Color.accentColor : Color.black.opacity(0.55),in:Circle())
                    .frame(width:44,height:44)
            }.buttonStyle(.plain).accessibilityLabel(selected ? "Deselect video" : "Select video")
        }
        .onAppear {
            let token = UUID()
            generation = token
            let options = PHImageRequestOptions()
            options.isNetworkAccessAllowed = true
            request = PHImageManager.default().requestImage(for:asset,targetSize:CGSize(width:400,height:300),contentMode:.aspectFill,options:options) { thumbnail,_ in
                DispatchQueue.main.async { if generation == token, let thumbnail { image = thumbnail } }
            }
        }.onDisappear {
            generation = UUID()
            if let request { PHImageManager.default().cancelImageRequest(request) }
        }
    }
}

struct MoviePreview: View {
    let asset: PHAsset
    @Environment(\.dismiss) private var dismiss
    @State private var player: AVPlayer?
    @State private var failed = false
    @State private var request: PHImageRequestID?
    @State private var generation = UUID()

    private func loadVideo() {
        failed = false
        let token = UUID()
        generation = token
        let options = PHVideoRequestOptions()
        options.isNetworkAccessAllowed = true
        request = PHImageManager.default().requestPlayerItem(forVideo:asset,options:options) { item,_ in
            DispatchQueue.main.async {
                guard generation == token else { return }
                guard let item else { failed = true; return }
                let playback = AVPlayer(playerItem:item)
                player = playback
                playback.play()
            }
        }
    }

    var body: some View {
        NavigationStack {
            Group {
                if let player { VideoPlayer(player:player) }
                else if failed {
                    VStack { Text("Couldn’t load this video from Photos."); Button("Try again",action:loadVideo) }
                } else { ProgressView("Loading video from Photos…") }
            }
            .navigationTitle("Preview").navigationBarTitleDisplayMode(.inline)
            .toolbar { Button("Done") { dismiss() } }
        }.onAppear(perform:loadVideo).onDisappear {
            generation = UUID()
            if let request { PHImageManager.default().cancelImageRequest(request) }
            player?.pause()
            player = nil
        }
    }
}

final class TransferMeter: ObservableObject {
    @Published var reading: (bytes:Int64,speed:Double?)?
}
struct TransferProgress: View {
    let job: Job
    @ObservedObject var meter: TransferMeter
    var body: some View {
        VStack(alignment:.leading,spacing:4) {
                let sent = min(job.bytes,job.confirmed + (meter.reading?.bytes ?? 0))
                let fraction = Double(sent) / Double(max(1,job.bytes))
                ProgressView(value:fraction)
                Text("\(Int(fraction * 100))% sent · \(bytes(sent)) of \(bytes(job.bytes))").monospacedDigit()
                if let speed = meter.reading?.speed, speed > 0, sent < job.bytes {
                    Text("\(bytes(Int64(speed)))/s · about \(Int(ceil(Double(job.bytes - sent) / speed))) s left")
                }
                if sent == job.bytes { Text("Waiting for YouTube to confirm receipt") }
        }
    }
}
struct BatchPicker: View {
    @EnvironmentObject var model: Model
    @Environment(\.dismiss) var dismiss
    @State private var selected = Set<UUID>()
    var body: some View {
        NavigationStack {
            List {
                Button("Select all queued") { selected = Set(model.jobs.filter { $0.phase == .queued }.map(\.id)) }
                ForEach(model.jobs.filter { $0.phase == .queued }) { job in
                    Button {
                        if !selected.insert(job.id).inserted { selected.remove(job.id) }
                    } label: {
                        HStack {
                            Image(systemName:selected.contains(job.id) ? "checkmark.circle.fill" : "circle")
                            VStack(alignment:.leading) { Text(job.filename); Text(job.privacy.capitalized + " · " + bytes(job.bytes)).font(.caption) }
                        }
                    }
                }
            }.navigationTitle("Select uploads")
            .toolbar { Button("Cancel") { dismiss() } }
            .safeAreaInset(edge:.bottom) {
                Button("Start selected (\(selected.count))") { model.startSelected(selected); dismiss() }
                    .disabled(selected.isEmpty || model.channel == nil).buttonStyle(.borderedProminent).padding()
            }
        }
    }
}
struct TransferRow: View {
    let job: Job
    @EnvironmentObject private var model: Model
    var body: some View {
        VStack(alignment:.leading,spacing:6) {
            NavigationLink(value:job.id) { Text(job.filename).font(.headline).lineLimit(2) }
            if job.phase == .uploading {
                TransferProgress(job:job,meter:model.meter(job.id))
            } else if job.phase == .queued {
                Text("Queued · \(bytes(job.bytes)) · \(job.privacy.capitalized)")
                Button("Start upload") { Task { await model.run(job.id) } }
                    .buttonStyle(.bordered).disabled(model.busy.contains(job.id) || model.channel == nil)
            } else {
                Text(job.phase.rawValue)
                if !job.detail.isEmpty { Text(job.detail).foregroundStyle(.secondary) }
            }
        }.font(.subheadline).padding(.vertical,3)
    }
}
