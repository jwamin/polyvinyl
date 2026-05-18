import SwiftUI

@main
struct PolyvinylApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
#if os(macOS)
                .frame(minWidth: 520, minHeight: 640)
#endif
        }
#if os(macOS)
        .windowResizability(.contentMinSize)
#endif
    }
}
