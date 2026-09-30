from qgis.PyQt.QtCore import QCoreApplication, QStandardPaths
from qgis.PyQt.QtNetwork import QNetworkProxy

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterBoolean,
    QgsProcessingException,
    QgsProject,
    QgsNetworkAccessManager,
    QgsVectorLayer,
    QgsRasterLayer,
    QgsPointCloudLayer
)

import os
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse, parse_qs, unquote, quote


class TelechargementAnnule(Exception):
    """Annulation demandée par l'utilisateur."""


def erreur_temporaire(erreur):

    # Seules les erreurs qui peuvent disparaître d'elles-mêmes
    # (délai dépassé, coupure réseau, serveur surchargé) valent
    # une nouvelle tentative ; pas un 404 ou un 403.

    if isinstance(erreur, urllib.error.HTTPError):
        return erreur.code >= 500 or erreur.code in (408, 429)

    return True


class TelechargerDonneesLidarIGN(QgsProcessingAlgorithm):

    TYPE_DONNEE = 'TYPE_DONNEE'
    DOSSIER = 'DOSSIER'
    AJOUTER = 'AJOUTER'

    NOM_COUCHE = 'IGNF_LIDAR-HD_METADONNEE:metadata'

    CHAMPS = {
        0: 'url_mnt',
        1: 'url_mns',
        2: 'url_mnh',
        3: 'url_npl'
    }

    NOMS_TYPES = {
        0: 'MNT',
        1: 'MNS',
        2: 'MNH',
        3: 'NPL'
    }

    NB_TENTATIVES = 3
    DELAI_REPONSE = 60

    # =========================================================
    # INFORMATIONS PROCESSING
    # =========================================================

    def tr(self, string):
        return QCoreApplication.translate(
            'TelechargerDonneesLidarIGN',
            string
        )

    def createInstance(self):
        return TelechargerDonneesLidarIGN()

    def name(self):
        return 'telecharger_donnees_lidar_ign'

    def displayName(self):
        return self.tr(
            '2 - Télécharger les données LiDAR IGN'
        )

    def group(self):
        return self.tr('LiDAR IGN')

    def groupId(self):
        return 'lidar_ign'

    # =========================================================
    # AIDE
    # =========================================================

    def shortHelpString(self):

        return self.tr(
            """
            <h2>Télécharger les données LiDAR HD IGN</h2>

            <p>
            Télécharge les données correspondant
            <b>uniquement aux dalles sélectionnées</b>.
            </p>

            <h3>Utilisation</h3>

            <ol>
                <li>
                    Chargez le dallage avec
                    <b>1 - Charger le dallage LiDAR IGN</b>.
                </li>

                <li>
                    Sélectionnez une ou plusieurs dalles.
                </li>

                <li>
                    Choisissez le produit :
                    MNT, MNS, MNH ou NPL.
                </li>

                <li>
                    Conservez le dossier proposé
                    ou choisissez-en un autre.
                </li>

                <li>
                    Cliquez sur <b>Exécuter</b>.
                </li>
            </ol>

            <p>
            <b>MNT</b> : Modèle numérique de terrain<br>
            <b>MNS</b> : Modèle numérique de surface<br>
            <b>MNH</b> : Modèle numérique de hauteur<br>
            <b>NPL</b> : Nuage de points LiDAR COPC.LAZ
            </p>

            <p>
            Les fichiers sont enregistrés par défaut dans
            <b>Téléchargements/LiDAR_IGN</b>.
            </p>

            <p>
            Les fichiers déjà présents ne sont pas
            téléchargés une seconde fois.
            </p>

            <p>
            Le téléchargement est effectué en arrière-plan.
            Les couches sont ajoutées au projet une fois
            les téléchargements terminés.
            </p>

            <p>
            <b>Important :</b>
            seules les dalles sélectionnées sont téléchargées.
            </p>
            """
        )

    # =========================================================
    # PARAMÈTRES
    # =========================================================

    def initAlgorithm(self, config=None):

        self.addParameter(
            QgsProcessingParameterEnum(
                self.TYPE_DONNEE,
                self.tr('Donnée à télécharger'),
                options=[
                    'MNT — Modèle numérique de terrain',
                    'MNS — Modèle numérique de surface',
                    'MNH — Modèle numérique de hauteur',
                    'NPL — Nuage de points LiDAR (COPC.LAZ)'
                ],
                defaultValue=0
            )
        )

        dossier_telechargements = (
            QStandardPaths.writableLocation(
                QStandardPaths.DownloadLocation
            )
        )

        if not dossier_telechargements:
            dossier_telechargements = os.path.expanduser("~")

        dossier_defaut = os.path.join(
            dossier_telechargements,
            "LiDAR_IGN"
        )

        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.DOSSIER,
                self.tr('Dossier de téléchargement'),
                defaultValue=dossier_defaut
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.AJOUTER,
                self.tr(
                    'Ajouter les données téléchargées au projet'
                ),
                defaultValue=True
            )
        )

    # =========================================================
    # RECHERCHE DU DALLAGE
    # =========================================================

    def trouver_couche_emprise(self, project):

        # La couche est reconnue à sa source WFS et non
        # à son nom : elle reste trouvée si l'utilisateur
        # la renomme.

        for layer in project.mapLayers().values():

            if (
                isinstance(layer, QgsVectorLayer)
                and layer.providerType() == 'WFS'
                and self.NOM_COUCHE in layer.source()
            ):
                return layer

        return None

    # =========================================================
    # PROXY
    # =========================================================

    def construire_opener(self):

        # Reprend le proxy HTTP configuré dans QGIS
        # (Préférences > Réseau), que urllib ignore
        # sinon. Sans proxy QGIS, urllib garde son
        # comportement habituel (variables d'environnement).

        proxy = (
            QgsNetworkAccessManager.instance()
            .fallbackProxy()
        )

        types_http = (
            QNetworkProxy.ProxyType.HttpProxy,
            QNetworkProxy.ProxyType.HttpCachingProxy
        )

        if proxy.type() in types_http and proxy.hostName():

            identifiants = ''

            if proxy.user():

                identifiants = (
                    f"{quote(proxy.user(), safe='')}:"
                    f"{quote(proxy.password(), safe='')}@"
                )

            adresse = (
                f"http://{identifiants}"
                f"{proxy.hostName()}:{proxy.port()}"
            )

            return urllib.request.build_opener(
                urllib.request.ProxyHandler({
                    'http': adresse,
                    'https': adresse
                })
            )

        return urllib.request.build_opener()

    # =========================================================
    # TÉLÉCHARGEMENT
    # =========================================================

    def telecharger(
        self,
        url,
        fichier,
        feedback,
        index_dalle,
        total_dalles
    ):

        # Écriture dans un fichier temporaire, renommé
        # seulement une fois le téléchargement complet :
        # un fichier interrompu n'est jamais pris pour
        # un fichier déjà présent.

        fichier_partiel = fichier + ".part"

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/130.0 Safari/537.36"
                ),
                "Referer": "https://geoservices.ign.fr/",
                "Accept": "*/*"
            }
        )

        try:

            with self.opener.open(
                request,
                timeout=self.DELAI_REPONSE
            ) as response:

                taille_totale = response.headers.get(
                    "Content-Length"
                )

                if taille_totale:

                    try:
                        taille_totale = int(taille_totale)
                    except Exception:
                        taille_totale = None

                telecharge = 0

                with open(fichier_partiel, "wb") as output:

                    while True:

                        if feedback.isCanceled():
                            raise TelechargementAnnule()

                        chunk = response.read(
                            1024 * 1024
                        )

                        if not chunk:
                            break

                        output.write(chunk)

                        telecharge += len(chunk)

                        if taille_totale:

                            progression_fichier = (
                                telecharge / taille_totale
                            )

                            progression_globale = (
                                (
                                    index_dalle
                                    + progression_fichier
                                )
                                / total_dalles
                            ) * 100

                            feedback.setProgress(
                                int(progression_globale)
                            )

                        # Taille inconnue : pas de barre de
                        # progression possible, on indique
                        # la quantité reçue tous les 50 Mo.

                        elif telecharge % (50 * 1024 * 1024) < len(chunk):

                            feedback.pushInfo(
                                f"    → "
                                f"{telecharge / (1024 * 1024):.0f}"
                                f" Mo reçus..."
                            )

            # =================================================
            # CONTRÔLE DE LA TAILLE
            # =================================================

            if taille_totale and telecharge != taille_totale:

                raise IOError(
                    f"téléchargement incomplet "
                    f"({telecharge} octets reçus "
                    f"sur {taille_totale})"
                )

            # =================================================
            # RENOMMAGE DU FICHIER COMPLET
            # =================================================

            os.replace(fichier_partiel, fichier)

        except Exception:

            if os.path.exists(fichier_partiel):

                try:
                    os.remove(fichier_partiel)
                except Exception:
                    pass

            raise

    # =========================================================
    # PRÉPARATION (THREAD PRINCIPAL)
    # =========================================================

    def prepareAlgorithm(
        self,
        parameters,
        context,
        feedback
    ):

        # Exécutée dans le thread principal de QGIS :
        # c'est ici, et non dans processAlgorithm (qui
        # tourne en arrière-plan), que la couche et sa
        # sélection peuvent être lues sans risque.

        # =====================================================
        # DALLAGE
        # =====================================================

        project = context.project()

        if project is None:
            project = QgsProject.instance()

        layer = self.trouver_couche_emprise(project)

        if layer is None:

            raise QgsProcessingException(
                "\n"
                "DALLAGE LIDAR IGN ABSENT\n\n"
                "Le dallage LiDAR IGN n'est pas présent "
                "dans le projet.\n\n"
                "Utilisez d'abord :\n\n"
                "« 1 - Charger le dallage LiDAR IGN »"
            )

        # =====================================================
        # SÉLECTION OBLIGATOIRE
        # =====================================================

        if layer.selectedFeatureCount() == 0:

            raise QgsProcessingException(
                "\n"
                "AUCUNE DALLE SÉLECTIONNÉE\n\n"
                "Sélectionnez une ou plusieurs dalles "
                "avant de lancer le téléchargement.\n\n"
                "Aucun téléchargement n'a été effectué."
            )

        # =====================================================
        # VÉRIFICATION DU CHAMP
        # =====================================================

        type_index = self.parameterAsEnum(
            parameters,
            self.TYPE_DONNEE,
            context
        )

        champ_url = self.CHAMPS[type_index]

        if champ_url not in layer.fields().names():

            raise QgsProcessingException(
                f"Le champ « {champ_url} » n'existe pas "
                "dans le dallage LiDAR IGN."
            )

        # =====================================================
        # COPIE DES URL DES DALLES SÉLECTIONNÉES
        # =====================================================

        self.dalles = [
            (feature.id(), feature[champ_url])
            for feature in layer.selectedFeatures()
        ]

        # =====================================================
        # CONNEXION (PROXY QGIS)
        # =====================================================

        self.opener = self.construire_opener()

        return True

    # =========================================================
    # TRAITEMENT PRINCIPAL
    # =========================================================

    def processAlgorithm(
        self,
        parameters,
        context,
        feedback
    ):

        self.fichiers_a_charger = []

        self.ajouter_apres = False

        self.nb_telecharges = 0
        self.nb_existants = 0
        self.nb_erreurs = 0

        # =====================================================
        # PARAMÈTRES
        # =====================================================

        type_index = self.parameterAsEnum(
            parameters,
            self.TYPE_DONNEE,
            context
        )

        dossier = self.parameterAsString(
            parameters,
            self.DOSSIER,
            context
        )

        ajouter = self.parameterAsBool(
            parameters,
            self.AJOUTER,
            context
        )

        self.ajouter_apres = ajouter

        # =====================================================
        # DOSSIER
        # =====================================================

        if not dossier:

            raise QgsProcessingException(
                "Aucun dossier de téléchargement "
                "n'a été défini."
            )

        dossier = os.path.expanduser(dossier)

        os.makedirs(
            dossier,
            exist_ok=True
        )

        self.dossier_final = dossier

        # =====================================================
        # PRODUIT
        # =====================================================

        nom_type = self.NOMS_TYPES[type_index]

        self.nom_type_final = nom_type

        # =====================================================
        # DÉBUT
        # =====================================================

        total = len(self.dalles)

        self.total_final = total

        feedback.pushInfo(
            f"{total} dalle(s) sélectionnée(s)"
        )

        feedback.pushInfo(
            f"Produit : {nom_type}"
        )

        feedback.pushInfo(
            f"Dossier : {dossier}"
        )

        feedback.pushInfo('')

        # =====================================================
        # BOUCLE
        # =====================================================

        for i, (fid, url) in enumerate(self.dalles):

            if feedback.isCanceled():
                break

            if not url:

                feedback.reportError(
                    f"Entité {fid} : URL absente."
                )

                self.nb_erreurs += 1
                continue

            url = str(url)

            try:

                # =============================================
                # NOM MNT / MNS / MNH
                # =============================================

                if type_index in (0, 1, 2):

                    params_url = parse_qs(
                        urlparse(url).query
                    )

                    nom = params_url.get(
                        'FILENAME',
                        [
                            f'{nom_type}_{fid}.tif'
                        ]
                    )[0]

                    # basename : le nom ne peut pas
                    # désigner un autre dossier (« ../ »).

                    nom = os.path.basename(unquote(nom))

                    if not nom:

                        nom = f'{nom_type}_{fid}.tif'

                # =============================================
                # NOM NPL
                # =============================================

                else:

                    nom = os.path.basename(
                        unquote(urlparse(url).path)
                    )

                    if not nom:

                        nom = (
                            f'LIDAR_'
                            f'{fid}.copc.laz'
                        )

                # =============================================
                # FICHIER LOCAL
                # =============================================

                fichier = os.path.join(
                    dossier,
                    nom
                )

                feedback.pushInfo(
                    f"[{i + 1}/{total}] {nom}"
                )

                # =============================================
                # TÉLÉCHARGEMENT
                # =============================================

                if not os.path.exists(fichier):

                    feedback.pushInfo(
                        "    → téléchargement..."
                    )

                    # Le serveur IGN ne répond parfois pas :
                    # on retente avant de compter une erreur.

                    for tentative in range(
                        1, self.NB_TENTATIVES + 1
                    ):

                        try:

                            self.telecharger(
                                url,
                                fichier,
                                feedback,
                                i,
                                total
                            )

                            break

                        except TelechargementAnnule:
                            raise

                        except Exception as e:

                            if (
                                tentative == self.NB_TENTATIVES
                                or not erreur_temporaire(e)
                            ):
                                raise

                            feedback.pushWarning(
                                f"    → échec ({e}), nouvelle "
                                f"tentative {tentative + 1}"
                                f"/{self.NB_TENTATIVES}..."
                            )

                            time.sleep(5)

                            if feedback.isCanceled():
                                raise TelechargementAnnule()

                    self.nb_telecharges += 1

                    taille_mo = (
                        os.path.getsize(fichier)
                        / (1024 * 1024)
                    )

                    feedback.pushInfo(
                        f"    → terminé "
                        f"({taille_mo:.1f} Mo)"
                    )

                else:

                    self.nb_existants += 1

                    taille_mo = (
                        os.path.getsize(fichier)
                        / (1024 * 1024)
                    )

                    feedback.pushInfo(
                        f"    → déjà présent "
                        f"({taille_mo:.1f} Mo)"
                    )

                    feedback.setProgress(
                        int(
                            ((i + 1) / total) * 100
                        )
                    )

                # =============================================
                # MÉMORISATION POUR LE THREAD PRINCIPAL
                # =============================================

                if ajouter:

                    self.fichiers_a_charger.append(
                        (
                            fichier,
                            nom,
                            type_index
                        )
                    )

            except TelechargementAnnule:
                break

            except Exception as e:

                feedback.reportError(
                    f"Erreur pour l'entité "
                    f"{fid} : {e}"
                )

                self.nb_erreurs += 1

        # =====================================================
        # ANNULATION
        # =====================================================

        # Après une annulation, QGIS n'appelle pas
        # postProcessAlgorithm : les couches ne peuvent pas
        # être ajoutées, mais les fichiers complets restent
        # dans le dossier et seront repris au prochain
        # lancement.

        if feedback.isCanceled():

            feedback.pushWarning(
                f"Annulé. {self.nb_telecharges} dalle(s) "
                f"téléchargée(s) conservée(s) dans {dossier}. "
                "Relancez avec la même sélection pour "
                "terminer et les ajouter au projet."
            )

            return {self.DOSSIER: dossier}

        feedback.pushInfo('')
        feedback.pushInfo(
            "Téléchargements terminés."
        )

        if ajouter:

            feedback.pushInfo(
                "Les couches vont maintenant être "
                "ajoutées au projet."
            )

        return {self.DOSSIER: dossier}

    # =========================================================
    # POST-TRAITEMENT
    # =========================================================

    def postProcessAlgorithm(
        self,
        context,
        feedback
    ):

        nb_charges = 0

        if self.ajouter_apres:

            project = context.project()

            if project is None:
                project = QgsProject.instance()

            # -------------------------------------------------
            # Fichiers déjà chargés
            # -------------------------------------------------

            sources_existantes = set()

            for lyr in project.mapLayers().values():

                try:

                    source = lyr.source()

                    if source and os.path.isfile(source):

                        sources_existantes.add(
                            os.path.abspath(source)
                        )

                except Exception:
                    pass

            # =================================================
            # AJOUT DES FICHIERS
            # =================================================

            for (
                fichier,
                nom,
                data_type
            ) in self.fichiers_a_charger:

                fichier_absolu = os.path.abspath(
                    fichier
                )

                if fichier_absolu in sources_existantes:

                    feedback.pushInfo(
                        f"    → {nom} déjà chargé "
                        "dans le projet"
                    )

                    continue

                try:

                    # =========================================
                    # RASTER
                    # =========================================

                    if data_type in (0, 1, 2):

                        couche = QgsRasterLayer(
                            fichier,
                            nom
                        )

                    # =========================================
                    # COPC
                    # =========================================

                    else:

                        options = (
                            QgsPointCloudLayer.LayerOptions()
                        )

                        options.loadDefaultStyle = True

                        couche = QgsPointCloudLayer(
                            fichier,
                            nom,
                            'copc',
                            options
                        )

                    # =========================================
                    # CONTRÔLE
                    # =========================================

                    if not couche.isValid():

                        feedback.reportError(
                            f"Impossible de charger : {nom}"
                        )

                        self.nb_erreurs += 1
                        continue

                    # =========================================
                    # AJOUT AU PROJET
                    # =========================================

                    project.addMapLayer(
                        couche
                    )

                    sources_existantes.add(
                        fichier_absolu
                    )

                    nb_charges += 1

                    couche.triggerRepaint()

                    feedback.pushInfo(
                        f"    → {nom} ajouté au projet"
                    )

                except Exception as e:

                    feedback.reportError(
                        f"Erreur lors de l'ajout de "
                        f"{nom} : {e}"
                    )

                    self.nb_erreurs += 1

        # =====================================================
        # BILAN FINAL
        # =====================================================

        feedback.pushInfo('')
        feedback.pushInfo(
            '=============================='
        )

        feedback.pushInfo(
            'LiDAR HD IGN — TERMINÉ'
        )

        feedback.pushInfo(
            '=============================='
        )

        feedback.pushInfo(
            f'Produit : {self.nom_type_final}'
        )

        feedback.pushInfo(
            f'Dalles sélectionnées : {self.total_final}'
        )

        feedback.pushInfo(
            f'Nouveaux téléchargements : '
            f'{self.nb_telecharges}'
        )

        feedback.pushInfo(
            f'Déjà présents : {self.nb_existants}'
        )

        if self.ajouter_apres:

            feedback.pushInfo(
                f'Couches ajoutées au projet : '
                f'{nb_charges}'
            )

        feedback.pushInfo(
            f'Erreurs : {self.nb_erreurs}'
        )

        feedback.pushInfo(
            f'Dossier : {self.dossier_final}'
        )

        return {self.DOSSIER: self.dossier_final}