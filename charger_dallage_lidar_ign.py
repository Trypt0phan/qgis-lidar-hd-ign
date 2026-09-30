from qgis.PyQt.QtCore import QCoreApplication

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProject,
    QgsVectorLayer
)


class ChargerDallageLidarIGN(QgsProcessingAlgorithm):

    NOM_COUCHE = 'IGNF_LIDAR-HD_METADONNEE:metadata'

    WFS_URI = (
        "restrictToRequestBBOX='1' "
        "srsname='EPSG:2154' "
        "typename='IGNF_LIDAR-HD_METADONNEE:metadata' "
        "url='https://data.geopf.fr/wfs/ows' "
        "url='https://data.geopf.fr/wfs/ows?VERSION=2.0.0' "
        "version='auto'"
    )

    def tr(self, string):
        return QCoreApplication.translate(
            'ChargerDallageLidarIGN',
            string
        )

    def createInstance(self):
        return ChargerDallageLidarIGN()

    def name(self):
        return 'charger_dallage_lidar_ign'

    def displayName(self):
        return self.tr('1 - Charger le dallage LiDAR IGN')

    def group(self):
        return self.tr('LiDAR IGN')

    def groupId(self):
        return 'lidar_ign'

    def shortHelpString(self):
        return self.tr(
            """
            <h2>Charger le dallage LiDAR HD IGN</h2>

            <p>
            Ajoute au projet QGIS la couche WFS représentant
            les emprises des dalles LiDAR HD de l'IGN.
            </p>

            <p>
            Une fois la couche chargée, sélectionnez les dalles
            souhaitées puis utilisez :
            <b>2 - Télécharger les données LiDAR IGN</b>.
            </p>
            """
        )

    def initAlgorithm(self, config=None):
        # Aucun paramètre nécessaire
        pass

    def processAlgorithm(
        self,
        parameters,
        context,
        feedback
    ):

        project = QgsProject.instance()

        # Vérifie si elle est déjà présente
        for layer in project.mapLayers().values():

            if (
                layer.name() == self.NOM_COUCHE
                and isinstance(layer, QgsVectorLayer)
            ):

                feedback.pushInfo(
                    "Le dallage LiDAR IGN est déjà présent "
                    "dans le projet."
                )

                return {}

        # Chargement du WFS
        feedback.pushInfo(
            "Connexion au WFS LiDAR HD IGN..."
        )

        layer = QgsVectorLayer(
            self.WFS_URI,
            self.NOM_COUCHE,
            'WFS'
        )

        if not layer.isValid():

            raise QgsProcessingException(
                "Impossible de charger le dallage "
                "LiDAR IGN depuis le WFS."
            )

        project.addMapLayer(layer)

        feedback.pushInfo(
            "Dallage LiDAR IGN ajouté au projet."
        )

        feedback.pushInfo(
            "Vous pouvez maintenant sélectionner "
            "les dalles à télécharger."
        )

        return {}