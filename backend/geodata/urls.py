from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AntennaEquipmentViewSet, AntennaSpecificationViewSet, TerrainLoadCalculationViewSet, TerrainClassificationViewSet

router = DefaultRouter()
router.register(r'antenna-equipment', AntennaEquipmentViewSet)
router.register(r'antenna-specifications', AntennaSpecificationViewSet)
router.register(r'terrain-calculations', TerrainLoadCalculationViewSet)
router.register(r'terrain-classification', TerrainClassificationViewSet, basename='terrain-classification')

app_name = 'geodata'

urlpatterns = [
    path('', include(router.urls)),
]
