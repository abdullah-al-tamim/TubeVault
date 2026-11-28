// swift-tools-version: 5.8
import PackageDescription
let package = Package(name: "TubeVaultCore", products: [.library(name: "TubeVaultCore", targets: ["TubeVaultCore"])],
    targets: [.target(name: "TubeVaultCore", path: "Core"), .testTarget(name: "CoreTests", dependencies: ["TubeVaultCore"], path: "Tests")])
