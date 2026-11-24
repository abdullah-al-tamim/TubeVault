import Foundation
import UIKit

final class Transfers: NSObject, URLSessionDataDelegate, URLSessionTaskDelegate {
    static let shared = Transfers()
    static let identifier = "tubevault.ios.upload.v1"
    var finished: (() -> Void)?
    private var bodies = [Int:Data]()
    lazy var session: URLSession = {
        let config = URLSessionConfiguration.background(withIdentifier: Self.identifier)
        config.sessionSendsLaunchEvents = true
        config.isDiscretionary = false
        return URLSession(configuration: config, delegate: self, delegateQueue: .main)
    }()
    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        if (bodies[dataTask.taskIdentifier]?.count ?? 0) + data.count <= 256 * 1024 { bodies[dataTask.taskIdentifier, default: Data()].append(data) }
    }
    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        guard let label = task.taskDescription, let id = UUID(uuidString: label) else { return }
        let data = bodies.removeValue(forKey: task.taskIdentifier) ?? Data()
        MainActor.assumeIsolated { Model.shared.received(id, response: task.response as? HTTPURLResponse, data: data, interrupted: error != nil) }
    }
    func urlSession(_ session: URLSession, task: URLSessionTask, didSendBodyData bytesSent: Int64, totalBytesSent: Int64, totalBytesExpectedToSend: Int64) {
        guard let label = task.taskDescription, let id = UUID(uuidString: label) else { return }
        MainActor.assumeIsolated { Model.shared.progress(id,count:totalBytesSent) }
    }
    func urlSessionDidFinishEvents(forBackgroundURLSession session: URLSession) {
        let callback = finished
        finished = nil
        callback?()
    }
}
final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication, handleEventsForBackgroundURLSession identifier: String, completionHandler: @escaping () -> Void) {
        guard identifier == Transfers.identifier else { completionHandler(); return }
        Transfers.shared.finished = completionHandler
        _ = Transfers.shared.session
    }
}
