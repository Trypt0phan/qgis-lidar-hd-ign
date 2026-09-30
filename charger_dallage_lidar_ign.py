from qgis.PyQt.QtCore import QCoreApplication

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
        return (
            super().flags()
            | Qgis.ProcessingAlgorithmFlag.NoThreading
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
        # -----------------------------------------------------

        for layer in project.mapLayers().values():

            if (
                isinstance(layer, QgsVectorLayer)
                and layer.name() == self.NOM_COUCHE
            ):

                feedback.pushInfo(
                    "Le dallage LiDAR IGN est déjà présent "
                    "dans le projet."
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

        feedback.pushInfo(
            "Dallage LiDAR HD IGN ajouté au projet."
        )

        feedback.pushInfo(
            "Sélectionnez maintenant les dalles "
            "à télécharger."
        )

        return {}