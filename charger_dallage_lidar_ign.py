from qgis.PyQt.QtCore import QCoreApplication
from qgis.utils import iface

from qgis.core import (
    Qgis,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProject,
    QgsVectorLayer
)


class ChargerDallageLidarIGN(QgsProcessingAlgorithm):

    NOM_COUCHE = "IGNF_LIDAR-HD_METADONNEE:metadata"

    # =========================================================
    # INFORMATIONS PROCESSING
    # =========================================================

    def tr(self, string):
        return QCoreApplication.translate(
            "ChargerDallageLidarIGN",
            string
        )

    def createInstance(self):
        return ChargerDallageLidarIGN()

    def name(self):
        return "charger_dallage_lidar_ign"

    def displayName(self):
        return self.tr(
            "1 - Charger le dallage LiDAR IGN"
        )

    def group(self):
        return self.tr("LiDAR IGN")

    def groupId(self):
        return "lidar_ign"

    def shortHelpString(self):
        return self.tr(
            """
            <h2>Charger le dallage LiDAR HD IGN</h2>

            <p>
            Charge dans le projet QGIS le dallage du
            LiDAR HD IGN depuis le service WFS de la
            Géoplateforme.
            </p>

            <p>
            Sélectionnez ensuite une ou plusieurs dalles
            puis utilisez :
            <b>2 - Télécharger les données LiDAR IGN</b>.
            </p>
            """
        )

    # =========================================================
    # AUCUN PARAMÈTRE
    # =========================================================

    def initAlgorithm(self, config=None):
        pass

    # =========================================================
    # THREAD PRINCIPAL QGIS
    # =========================================================

    def flags(self):

        # Qgis.ProcessingAlgorithmFlag n'existe qu'à
        # partir de QGIS 3.36.

        try:
            sans_thread = (
                Qgis.ProcessingAlgorithmFlag.NoThreading
            )
        except AttributeError:
            sans_thread = (
                QgsProcessingAlgorithm.FlagNoThreading
            )

        return super().flags() | sans_thread

    # =========================================================
    # MESSAGES
    # =========================================================

    def informer(self, feedback, message, niveau=Qgis.Info):

        # Sans paramètre, l'algorithme est lancé sans
        # fenêtre ni journal : le message est donc aussi
        # affiché dans la barre de messages de QGIS.

        feedback.pushInfo(message)

        if iface is not None:

            iface.messageBar().pushMessage(
                "LiDAR IGN",
                message,
                niveau,
                5
            )

    # =========================================================
    # TRAITEMENT
    # =========================================================

    def processAlgorithm(
        self,
        parameters,
        context,
        feedback
    ):

        project = context.project()

        if project is None:
            project = QgsProject.instance()

        # -----------------------------------------------------
        # Vérifie si le dallage est déjà présent
        # (reconnu à sa source WFS, même s'il a été renommé)
        # -----------------------------------------------------

        for layer in project.mapLayers().values():

            if (
                isinstance(layer, QgsVectorLayer)
                and layer.providerType() == "WFS"
                and self.NOM_COUCHE in layer.source()
            ):

                self.informer(
                    feedback,
                    f"Le dallage LiDAR IGN est déjà présent "
                    f"dans le projet (couche « {layer.name()} »)."
                )

                return {}

        # =====================================================
        # CONNEXION WFS
        # =====================================================

        uri = (
            "restrictToRequestBBOX='1' "
            "srsname='EPSG:2154' "
            "typename='IGNF_LIDAR-HD_METADONNEE:metadata' "
            "url='https://data.geopf.fr/wfs/ows?VERSION=2.0.0' "
            "version='auto'"
        )

        feedback.pushInfo(
            "Connexion au WFS LiDAR HD IGN..."
        )

        # =====================================================
        # CRÉATION DE LA COUCHE
        # =====================================================

        layer = QgsVectorLayer(
            uri,
            self.NOM_COUCHE,
            "WFS"
        )

        if not layer.isValid():

            raise QgsProcessingException(
                "Impossible de charger le dallage "
                "LiDAR HD IGN depuis le WFS."
            )

        # =====================================================
        # AJOUT AU PROJET
        # =====================================================

        project.addMapLayer(layer)

        layer.triggerRepaint()

        self.informer(
            feedback,
            "Dallage LiDAR HD IGN ajouté au projet. "
            "Sélectionnez maintenant les dalles "
            "à télécharger.",
            Qgis.Success
        )

        return {}