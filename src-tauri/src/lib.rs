mod backend;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .plugin(tauri_plugin_dialog::init())
    // Il webview non sa aprire una pagina esterna: WKWebView chiede al
    // delegato una nuova vista per `target="_blank"`, Tauri non ne registra
    // nessuno e il click cade nel vuoto — nessuna scheda, nessun errore.
    // Il ponte lato pagina (frontend/components/external-link-bridge.tsx)
    // intercetta quei click e li consegna a questo plugin, che li passa al
    // browser di sistema. Lo scope in capabilities/default.json lo limita a
    // http/https: l'app non ha motivo di aprire altro.
    .plugin(tauri_plugin_opener::init())
    // Lo stato del processo figlio del backend: vuoto finche' `backend::avvia_e_attendi`
    // non lo riempie, cosi' l'handler di uscita qui sotto non prova mai a
    // terminare un figlio che non e' mai partito.
    .manage(backend::BackendProcess::empty())
    .setup(|app| {
      // Anche in release, di proposito. Un'app impacchettata che fallisce
      // l'avvio senza scrivere una riga e' indiagnosticabile: l'utente vede
      // un'icona che rimbalza e nient'altro, e chi la assiste non ha niente
      // da leggere. Il plugin scrive in ~/Library/Logs/<identifier>/.
      app.handle().plugin(
        tauri_plugin_log::Builder::default()
          .level(log::LevelFilter::Info)
          .build(),
      )?;

      // La finestra principale parte nascosta (vedi "visible": false in
      // tauri.conf.json) e viene mostrata solo da `avvia_e_attendi` dopo che
      // il backend ha risposto: mostrarla prima darebbe una pagina bianca o
      // un muro di errori di rete mentre uvicorn e' ancora in salita.
      //
      // Il controllo della porta, l'avvio del backend e l'attesa girano su
      // un thread di sistema dedicato, non nell'hook di `setup`: la guida
      // ufficiale di Tauri per gli schermi di avvio raccomanda di non
      // bloccare `setup` con lavoro di rete, perche' l'event loop deve poter
      // partire subito. Qui c'e' anche un motivo pratico: un eventuale
      // dialogo d'errore nativo va mostrato DOPO che l'event loop e' vivo,
      // altrimenti non c'e' alcun run loop a farlo comparire.
      let handle = app.handle().clone();
      std::thread::spawn(move || backend::avvia_e_attendi(handle));

      Ok(())
    })
    .build(tauri::generate_context!())
    .expect("error while running tauri application")
    .run(|app_handle, event| {
      // Comportamento 4: qualunque sia la via d'uscita (finestra chiusa,
      // Cmd+Q, un dialogo d'errore che ha chiamato app.exit), il figlio va
      // terminato PRIMA che il processo del guscio finisca di uscire.
      // Lasciarlo vivo attaccato alla porta 8000 e' l'orfano che il prossimo
      // avvio scambierebbe per "un altro programma la occupa".
      if let tauri::RunEvent::Exit = event {
        backend::termina(app_handle);
      }
    });
}
