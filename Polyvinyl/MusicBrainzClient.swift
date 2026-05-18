import Foundation

struct MusicBrainzResult {
    let artistCredit: String
    let releaseTitle: String
    let trackTitles: [String]
}

enum MusicBrainzError: Error, LocalizedError {
    case noResults, network(Int), decoding
    var errorDescription: String? {
        switch self {
        case .noResults: "No releases found on MusicBrainz"
        case .network(let c): "HTTP \(c)"
        case .decoding: "Invalid response from MusicBrainz"
        }
    }
}

actor MusicBrainzClient {
    private let userAgent: String
    private var lastRequest: Date = .distantPast
    private let throttleInterval: TimeInterval = 1.1

    init(appVersion: String) {
        userAgent = "Polyvinyl/\(appVersion) (+https://musicbrainz.org/doc/MusicBrainz_API)"
    }

    func lookup(artist: String?, album: String?, pickIndex: Int = 0) async throws -> MusicBrainzResult {
        var parts: [String] = []
        if let a = artist, !a.isEmpty { parts.append("artist:\"\(a)\"") }
        if let b = album, !b.isEmpty { parts.append("release:\"\(b)\"") }
        guard !parts.isEmpty else { throw MusicBrainzError.noResults }

        var comps = URLComponents(string: "https://musicbrainz.org/ws/2/release/")!
        comps.queryItems = [
            .init(name: "query", value: parts.joined(separator: " AND ")),
            .init(name: "fmt", value: "json"),
            .init(name: "limit", value: "10"),
        ]
        await wait()
        let searchData = try await fetch(comps.url!)

        guard let json = try? JSONSerialization.jsonObject(with: searchData) as? [String: Any],
              let releases = json["releases"] as? [[String: Any]], !releases.isEmpty
        else { throw MusicBrainzError.noResults }

        let pick = releases[min(pickIndex, releases.count - 1)]
        guard let mbid = pick["id"] as? String else { throw MusicBrainzError.decoding }

        var detailComps = URLComponents(string: "https://musicbrainz.org/ws/2/release/\(mbid)")!
        detailComps.queryItems = [
            .init(name: "fmt", value: "json"),
            .init(name: "inc", value: "artist-credits+recordings+release-groups"),
        ]
        await wait()
        let detailData = try await fetch(detailComps.url!)

        guard let d = try? JSONSerialization.jsonObject(with: detailData) as? [String: Any]
        else { throw MusicBrainzError.decoding }

        let releaseTitle = d["title"] as? String ?? "Unknown Album"
        var artistCredit = ""
        if let credits = d["artist-credit"] as? [[String: Any]] {
            artistCredit = credits
                .compactMap { ($0["artist"] as? [String: Any])?["name"] as? String }
                .joined(separator: " & ")
        }

        var trackTitles: [String] = []
        if let media = d["media"] as? [[String: Any]],
           let first = media.first,
           let tracks = first["tracks"] as? [[String: Any]] {
            trackTitles = tracks.compactMap {
                ($0["recording"] as? [String: Any])?["title"] as? String ?? $0["title"] as? String
            }
        }

        return MusicBrainzResult(artistCredit: artistCredit, releaseTitle: releaseTitle, trackTitles: trackTitles)
    }

    private func wait() async {
        let elapsed = Date().timeIntervalSince(lastRequest)
        if elapsed < throttleInterval {
            try? await Task.sleep(for: .seconds(throttleInterval - elapsed))
        }
        lastRequest = Date()
    }

    private func fetch(_ url: URL) async throws -> Data {
        var req = URLRequest(url: url)
        req.setValue(userAgent, forHTTPHeaderField: "User-Agent")
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse, http.statusCode == 200 else {
            throw MusicBrainzError.network((resp as? HTTPURLResponse)?.statusCode ?? -1)
        }
        return data
    }
}
