"""Encoded starting XIs (name as in passes.csv -> position group) for the
WC2026 games we have confident lineups for. Used to calibrate the model on
real results. Position groups: GK, CB, FB, DM, CM, AM, W, ST.

Each game: (title, [(teamA_name, [(player, pos)...]), (teamB_name, [...])]).
Only starters. Possession is derived from each team's share of starter passes.
"""

GAMES = [
    ("Belgium vs Egypt", [
        ("Belgium", [
            ("T. Courtois","GK"),("T. Meunier","FB"),("N. Ngoy","CB"),("B. Mechele","CB"),
            ("T. Castagne","FB"),("A. Onana","DM"),("Y. Tielemans","DM"),("J. Doku","W"),
            ("K. De Bruyne","AM"),("L. Trossard","W"),("C. De Ketelaere","ST")]),
        ("Egypt", [
            ("Mostafa Shobeir","GK"),("Ahmed Fatouh","FB"),("Hamdi Fathy","CB"),
            ("Yasser Ibrahim","CB"),("Mohamed Hany","FB"),("Marwan Attia","DM"),
            ("Mohanad Lasheen","DM"),("Mostafa Zico","W"),("Emam Ashour","AM"),
            ("Mohamed Salah","W"),("Omar Marmoush","ST")]),
    ]),
    ("Spain vs Cabo Verde", [
        ("Spain", [
            ("Unai Simón","GK"),("Marcos Llorente","FB"),("Pau Cubarsí","CB"),
            ("Aymeric Laporte","CB"),("Marc Cucurella","FB"),("Rodri","DM"),
            ("Pedri","CM"),("Fabián Ruiz","CM"),("Ferran Torres","W"),("Gavi","AM"),
            ("Mikel Oyarzabal","ST")]),
        # Cabo Verde XI/positions uncertain -> possession pinned (Spain 74%).
    ], 0.74),
    ("Tunisia vs Sweden", [
        ("Sweden", [
            ("K. Nordfeldt","GK"),("G. Lagerbielke","CB"),("I. Hien","CB"),("V. Lindelöf","CB"),
            ("A. Bernhardsson","FB"),("J. Karlström","DM"),("Y. Ayari","CM"),
            ("G. Gudmundsson","FB"),("B. Nygren","AM"),("V. Gyökeres","ST"),("A. Isak","ST")]),
        ("Tunisia", [
            ("A. Chamakh","GK"),("M. Ben Hmida","FB"),("O. Rekik","CB"),("M. Talbi","CB"),
            ("Y. Valery","FB"),("E. Skhiri","DM"),("R. Khedira","DM"),("A. Abdi","W"),
            ("H. Mejbri","AM"),("A. Ben Slimane","W"),("E. Saad","ST")]),
    ]),
    ("Ivory Coast vs Ecuador", [
        ("Ivory Coast", [
            ("Y. Fofana","GK"),("G. Doué","FB"),("W. Singo","CB"),("E. Agbadou","CB"),
            ("G. Konan","FB"),("Y. Diomande","W"),("S. Fofana","CM"),("F. Kessie","CM"),
            ("B. Touré","W"),("N. Pépé","ST"),("E. Wahi","ST")]),
        ("Ecuador", [
            ("H. Galíndez","GK"),("P. Hincapié","CB"),("W. Pacho","CB"),("J. Ordoñez","CB"),
            ("P. Vite","FB"),("M. Caicedo","DM"),("A. Franco","CM"),("A. Minda","FB"),
            ("J. Yeboah","W"),("E. Valencia","ST"),("G. Plata","W")]),
    ]),
    ("Netherlands vs Japan", [
        ("Netherlands", [
            ("B. Verbruggen","GK"),("D. Dumfries","FB"),("J. van Hecke","CB"),("V. van Dijk","CB"),
            ("M. van de Ven","FB"),("F. de Jong","DM"),("R. Gravenberch","CM"),("T. Reijnders","CM"),
            ("C. Summerville","W"),("D. Malen","ST"),("C. Gakpo","W")]),
        ("Japan", [
            ("Z. Suzuki","GK"),("H. Ito","CB"),("S. Taniguchi","CB"),("T. Watanabe","CB"),
            ("K. Nakamura","FB"),("K. Sano","DM"),("D. Kamada","CM"),("R. Doan","FB"),
            ("D. Maeda","W"),("T. Kubo","AM"),("A. Ueda","ST")]),
    ]),
    ("Turkey vs Australia", [
        ("Turkey", [
            ("U. Çakır","GK"),("F. Kadıoğlu","FB"),("A. Bardakcı","CB"),("M. Demiral","CB"),
            ("Z. Çelik","FB"),("İ. Yüksek","DM"),("H. Çalhanoğlu","DM"),("B. Yılmaz","W"),
            ("O. Kökçü","AM"),("A. Güler","W"),("K. Aktürkoğlu","ST")]),
        ("Australia", [
            ("P. Beach","GK"),("A. Circati","CB"),("H. Souttar","CB"),("C. Burgess","CB"),
            ("J. Italiano","FB"),("A. O'Neill","DM"),("P. Okon-Engstler","CM"),("J. Bos","FB"),
            ("N. Irankunda","W"),("C. Metcalfe","AM"),("M. Touré","ST")]),
    ]),
    ("Haiti vs Scotland", [
        ("Haiti", [
            ("J. Placide","GK"),("C. Arcus","FB"),("R. Adé","CB"),("H. Delcroix","CB"),
            ("M. Expérience","FB"),("L. Deedson","W"),("D. Jean Jacques","CM"),("J. Bellegarde","CM"),
            ("R. Providence","W"),("F. Pierrot","ST"),("W. Isidor","ST")]),
        ("Scotland", [
            ("A. Gunn","GK"),("A. Robertson","FB"),("G. Hanley","CB"),("J. Hendry","CB"),
            ("A. Hickey","FB"),("J. McGinn","W"),("L. Ferguson","CM"),("S. McTominay","CM"),
            ("B. Gannon-Doak","W"),("C. Adams","ST"),("L. Shankland","ST")]),
    ]),
    ("Brazil vs Morocco", [
        ("Brazil", [
            ("Alisson Becker","GK"),("Roger Ibañez","FB"),("Marquinhos","CB"),
            ("Gabriel Magalhães","CB"),("Douglas Santos","FB"),("Casemiro","DM"),
            ("Bruno Guimarães","DM"),("Raphinha","W"),("Lucas Paquetá","AM"),
            ("Vinícius Júnior","W"),("Igor Thiago","ST")]),
        ("Morocco", [
            ("Y. Bounou","GK"),("A. Hakimi","FB"),("I. Diop","CB"),("C. Riad","CB"),
            ("N. Mazraoui","FB"),("N. El Aynaoui","DM"),("A. Bouaddi","DM"),
            ("B. El Khannouss","W"),("A. Ounahi","AM"),("B. Díaz","W"),("I. Saibari","ST")]),
    ]),
    ("Qatar vs Switzerland", [
        ("Switzerland", [
            ("G. Kobel","GK"),("D. Zakaria","FB"),("N. Elvedi","CB"),("M. Akanji","CB"),
            ("R. Rodríguez","FB"),("M. Aebischer","CM"),("G. Xhaka","DM"),("R. Freuler","CM"),
            ("D. Ndoye","W"),("B. Embolo","ST"),("R. Vargas","W")]),
        ("Qatar", [
            ("Mahmud Abunada","GK"),("Ayoub Al Oui","FB"),("Pedro Miguel","CB"),
            ("Boualem Khoukhi","CB"),("Homam El Amin","FB"),("Jassem Gaber","CM"),
            ("Assim Madibo","CM"),("Issa Laye","CM"),("Edmílson Junior","W"),
            ("Yusuf Abdurisag","ST"),("Akram Afif","W")]),
    ]),
]
