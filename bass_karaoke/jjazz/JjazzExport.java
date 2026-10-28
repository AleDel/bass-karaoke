package bk;

import java.io.File;
import java.util.Locale;
import java.util.concurrent.Future;
import java.util.logging.Level;
import java.util.logging.Logger;
import org.jjazz.midimix.api.MidiMix;
import org.jjazz.midimix.spi.MidiMixManager;
import org.jjazz.musiccontrol.api.PlaybackSettings;
import org.jjazz.musiccontrol.api.SongMidiExporter;
import org.jjazz.rhythmdatabase.api.DefaultRhythmDatabaseImpl;
import org.jjazz.rhythmdatabase.api.RhythmDatabase;
import org.jjazz.rhythmdatabase.spi.SharedRdbInstanceProvider;
import org.jjazz.song.api.Song;
import org.jjazz.song.spi.SongFactory;
import org.openide.util.NbPreferences;

/**
 * Convierte un .sng de JJazzLab a MIDI usando el propio motor de JJazzLab
 * (JJazzLab Toolkit). Uso: {@code JjazzExport <in.sng> <out.mid>}.
 * <p>
 * La JVM debe arrancarse con {@code --add-opens=java.base/java.util=ALL-UNNAMED}
 * (XStream lo necesita para deserializar los {@code EnumSet} de
 * {@code ChordRenderingInfo}).
 */
public final class JjazzExport
{

    static
    {
        System.setProperty("java.util.logging.SimpleFormatter.format", "%4$s %3$s  %5$s %n");
        Locale.setDefault(Locale.ENGLISH);
    }
    private static final Logger LOGGER = Logger.getLogger(JjazzExport.class.getSimpleName());

    public static void main(String[] args)
    {
        if (args.length < 2)
        {
            System.err.println("uso: JjazzExport <in.sng> <out.mid>");
            System.exit(64);
        }
        File sngFile = new File(args[0]);
        File midFile = new File(args[1]);
        if (!sngFile.isFile())
        {
            System.err.println("no existe: " + sngFile);
            System.exit(66);
        }

        try
        {
            // La base de ritmos es un servicio que la app registra; aquí lo
            // creamos a mano (ver META-INF/services en el jar del puente).
            var rdbProvider = SharedRdbInstanceProvider.getDefault();
            if (rdbProvider == null)
            {
                System.err.println("sin SharedRdbInstanceProvider");
                System.exit(70);
            }
            RhythmDatabase rdb = rdbProvider.get();
            if (rdb == null || rdb.getRhythms().isEmpty())
            {
                System.err.println("base de ritmos vacía");
                System.exit(70);
            }

            // Sin click ni precount: el MIDI debe empezar en el compás 1.
            var ps = PlaybackSettings.getInstance();
            ps.setPlaybackClickEnabled(false);
            ps.setClickPrecountEnabled(false);

            Song song = SongFactory.getDefault().loadFromFile(sngFile);
            MidiMix midiMix = MidiMixManager.getDefault().createMix(song);

            if (!SongMidiExporter.songToMidiFile(song, midiMix, midFile, null))
            {
                System.err.println("SongMidiExporter falló");
                System.exit(70);
            }
            System.out.println("OK " + midFile.getAbsolutePath() + " " + midFile.length());
            System.exit(0);
        } catch (Throwable t)
        {
            LOGGER.log(Level.SEVERE, "error exportando " + sngFile, t);
            System.exit(70);
        }
    }

    /** Implementación mínima de la base de ritmos (la que usa la demo). */
    public static final class RdbProvider implements SharedRdbInstanceProvider
    {

        private DefaultRhythmDatabaseImpl rdb;

        public RdbProvider()
        {
        }

        @Override
        public Future<?> initialize()
        {
            rdb = new DefaultRhythmDatabaseImpl(NbPreferences.forModule(getClass()));
            rdb.addRhythmsFromRhythmProviders(false, false, false);
            return null;
        }

        @Override
        public boolean isInitialized()
        {
            return rdb != null;
        }

        @Override
        public RhythmDatabase get()
        {
            if (!isInitialized())
            {
                initialize();
            }
            return rdb;
        }

        @Override
        public void markForStartupRefresh(boolean b)
        {
        }

        @Override
        public boolean isMarkedForStartupRefresh()
        {
            return false;
        }
    }
}
