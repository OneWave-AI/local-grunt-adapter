import AppKit
import WebKit

final class PanelDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKScriptMessageHandler {
    var window: NSWindow!
    var web: WKWebView!
    let descriptor: String
    init(_ path: String) { descriptor = path }
    func applicationDidFinishLaunching(_ notification: Notification) {
        let config = WKWebViewConfiguration()
        config.userContentController.add(self, name: "closePanel")
        config.websiteDataStore = .nonPersistent()
        web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = self
        web.setValue(false, forKey: "drawsBackground")
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1040, height: 780), styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView], backing: .buffered, defer: false)
        window.title = "Local Grunt Adapter"
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        window.backgroundColor = NSColor(calibratedRed: 0.043, green: 0.055, blue: 0.071, alpha: 1)
        window.minSize = NSSize(width: 700, height: 540)
        window.contentView = web
        window.center()
        reload()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
    func reload() {
        guard let data = try? Data(contentsOf: URL(fileURLWithPath: descriptor)),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let value = object["url"] as? String, let url = URL(string: value),
              url.host == "127.0.0.1" else { return }
        web.load(URLRequest(url: url))
    }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        reload(); window.makeKeyAndOrderFront(nil); return true
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
        if message.name == "closePanel" { window.close() }
    }
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url, url.host == "127.0.0.1", url.scheme == "http" else { decisionHandler(.cancel); return }
        decisionHandler(.allow)
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.regular)
let defaultDescriptor = Bundle.main.bundleURL.deletingLastPathComponent().appendingPathComponent(".state/panel.json").path
let delegate = PanelDelegate(CommandLine.arguments.dropFirst().first ?? defaultDescriptor)
app.delegate = delegate
app.run()
